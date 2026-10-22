"""One recording → one assessment (HLD §5, LLD §5.19). Owns the order of the steps; the app and
scripts/evaluate.py both run it.

probe → speech-to-text → text quality → pseudonymise → roles (Claude) → metrics → video checks at
teacher-speech moments → payload → rubric judgement (Claude) → grade. Without audio, speech or AI,
the video checks still run and are reported without a grade.
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
from classlens.models import (
    UNKNOWN_SPEAKER,
    GradeResult,
    InteractionMetrics,
    MediaInfo,
    PseudonymisedTranscript,
    Transcript,
    TranscriptQuality,
    VideoFindings,
)
from classlens.privacy import PrivacyError, Pseudonymiser
from classlens.scoring import Scorer
from classlens.transcript import TranscriptAnalyzer
from classlens.video import VideoAnalyzer, VideoError, describe, sample_times

NO_AUDIO = "This recording has no audio, so the teaching could not be assessed. Only the camera and screen checks ran."
NO_SPEECH = "No speech was found in the audio, so the teaching could not be assessed. Only the camera and screen checks ran."


@dataclass(frozen=True)
class Assessment:
    """Everything the report shows. grade is None when the class could not be assessed; note says why.
    video is None when the frames could not be read."""

    media: MediaInfo
    quality: TranscriptQuality | None = None
    metrics: InteractionMetrics | None = None
    judge: JudgeResult | None = None
    grade: GradeResult | None = None
    note: str | None = None
    video: VideoFindings | None = None


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
            return Assessment(media, note=NO_AUDIO, video=self._check_video(video_path, None, media, facts, on_step))

        on_step("Turning speech into text on this server (the longest step)…")
        started = time.perf_counter()
        transcript = self.transcriber.transcribe(video_path)
        facts.update(transcription_s=round(time.perf_counter() - started, 1), lines=len(transcript.cues),
                     words=sum(cue.words for cue in transcript.cues))
        if not transcript.cues:
            return Assessment(media, note=NO_SPEECH, video=self._check_video(video_path, None, media, facts, on_step))
        quality = TranscriptAnalyzer(transcript).quality(media.duration_s)
        clean = Pseudonymiser(UNKNOWN_SPEAKER, self.known_names).apply(transcript)

        try:
            on_step("Labelling teacher and student lines…")
            labelled = self.labeller.label(clean)
        except (AIUnavailable, PrivacyError) as err:
            facts["ai_skipped"] = type(err).__name__
            video = self._check_video(video_path, None, media, facts, on_step)
            return Assessment(media, quality, note=str(err), video=video)
        return self._assess(video_path, media, quality, labelled, facts, on_step)

    def _assess(self, video_path: Path, media: MediaInfo, quality: TranscriptQuality,
                labelled: PseudonymisedTranscript, facts: dict, on_step) -> Assessment:
        """Metrics, video checks at the teacher's lines, rubric judgement, grade."""
        metrics = InteractionAnalyzer(labelled.transcript).compute()
        video = self._check_video(video_path, labelled.transcript, media, facts, on_step)
        try:
            on_step("Assessing the class against the rubric…")
            findings = describe(video) if video else []
            result = self.judge.assess(PromptBuilder(findings).build(labelled, metrics, quality, media.duration_s))
        except (AIUnavailable, PrivacyError) as err:
            facts["ai_skipped"] = type(err).__name__
            return Assessment(media, quality, metrics, note=str(err), video=video)

        grade = Scorer().grade(result.judgement, video)
        facts.update(grade=grade.grade, score=grade.score, holistic_grade=result.judgement.holistic_grade,
                     gate_flags=len(grade.flags))
        return Assessment(media, quality, metrics, result, grade, video=video)

    @staticmethod
    def _check_video(video_path: Path, transcript: Transcript | None, media: MediaInfo, facts: dict,
                     on_step) -> VideoFindings | None:
        """Frames at the teacher's lines (evenly spaced without a labelled transcript). None when the
        frames can't be read: C6 and C7 then rest on the transcript alone."""
        on_step("Checking camera, face and screen in sampled frames…")
        started = time.perf_counter()
        try:
            video = VideoAnalyzer(video_path).analyse(sample_times(transcript, media.duration_s))
        except VideoError:
            facts["video_skipped"] = True
            return None
        facts.update(video_s=round(time.perf_counter() - started, 1), frames=video.frames)
        return video
