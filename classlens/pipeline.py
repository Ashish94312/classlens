"""One recording → one assessment (HLD §5, LLD §5.19). Owns the order of the steps; the app and
scripts/evaluate.py both run it.

probe → speech-to-text → text quality → pseudonymise → roles (Claude) → metrics → payload →
rubric judgement (Claude) → grade. Video and audio checks join in phase 3.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from classlens.ingest import probe
from classlens.llm.claude import AIUnavailable
from classlens.llm.judge import ClaudeJudge, JudgeResult
from classlens.llm.prompt import PromptBuilder
from classlens.llm.roles import RoleLabeller
from classlens.metrics import InteractionAnalyzer
from classlens.models import UNKNOWN_SPEAKER, GradeResult, InteractionMetrics, MediaInfo, TranscriptQuality
from classlens.privacy import PrivacyError, Pseudonymiser
from classlens.scoring import Scorer
from classlens.transcript import TranscriptAnalyzer

NO_AUDIO = "This recording has no audio, so there is no transcript to assess. Visual checks are not available yet."
NO_SPEECH = "No speech was found in the audio, so the class could not be assessed."


@dataclass(frozen=True)
class Assessment:
    """Everything the report shows. grade is None when the class could not be assessed; note says why."""

    media: MediaInfo
    quality: TranscriptQuality | None = None
    metrics: InteractionMetrics | None = None
    judge: JudgeResult | None = None
    grade: GradeResult | None = None
    note: str | None = None


class AssessmentPipeline:
    """The steps for one recording. Collaborators are injected so tests and scripts can swap them."""

    def __init__(self, transcriber, labeller: RoleLabeller | None = None, judge: ClaudeJudge | None = None,
                 known_names: frozenset[str] = frozenset()):
        self.transcriber = transcriber  # anything with transcribe(path) -> Transcript
        self.known_names = known_names  # casefolded names always replaced (evaluation: the local real-name list)
        self.labeller = labeller or RoleLabeller()
        self.judge = judge or ClaudeJudge()

    def run(self, video_path: Path, facts: dict, on_step=lambda text: None) -> Assessment:
        """Adds counts and timings to facts as it goes (for the run log). on_step(text) reports progress."""
        media = probe(video_path)
        facts.update(video_min=round(media.duration_s / 60, 1), has_audio=media.has_audio)
        if not media.has_audio:
            return Assessment(media, note=NO_AUDIO)

        on_step("Turning speech into text on this server (the longest step)…")
        started = time.perf_counter()
        transcript = self.transcriber.transcribe(video_path)
        facts.update(transcription_s=round(time.perf_counter() - started, 1), lines=len(transcript.cues),
                     words=sum(cue.words for cue in transcript.cues))
        if not transcript.cues:
            return Assessment(media, note=NO_SPEECH)
        quality = TranscriptAnalyzer(transcript).quality(media.duration_s)
        clean = Pseudonymiser(UNKNOWN_SPEAKER, self.known_names).apply(transcript)

        try:
            on_step("Labelling teacher and student lines…")
            labelled = self.labeller.label(clean)
            metrics = InteractionAnalyzer(labelled.transcript).compute()
            on_step("Assessing the class against the rubric…")
            result = self.judge.assess(PromptBuilder().build(labelled, metrics, quality, media.duration_s))
        except (AIUnavailable, PrivacyError) as err:
            facts["ai_skipped"] = type(err).__name__
            return Assessment(media, quality, note=str(err))

        grade = Scorer().grade(result.judgement)
        facts.update(grade=grade.grade, score=grade.score, holistic_grade=result.judgement.holistic_grade)
        return Assessment(media, quality, metrics, result, grade)
