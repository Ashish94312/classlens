"""Deterministic interaction metrics from a pseudonymised transcript (HLD §6.2, LLD §5.6)."""

import re

from classlens import config
from classlens.models import TEACHER_CODE, UNKNOWN_SPEAKER, Cue, InteractionMetrics, Transcript

# A person code in the text: "N1" (someone named in speech) or "S3" (a Zoom speaker, offline VTTs)
NAMED_PERSON = re.compile(r"\b[SN]\d+\b")
MIN_MINUTES = 1 / 60  # avoids dividing by zero on a one-cue transcript


class InteractionAnalyzer:
    """Computes InteractionMetrics from a pseudonymised transcript (speakers T, S, Unknown). Anything
    not by T counts as student speech, so it also works on Zoom VTTs (S1, S2…)."""

    def __init__(self, transcript: Transcript):
        self.transcript = transcript
        self.speech = [cue for cue in transcript.speech() if cue.speaker != UNKNOWN_SPEAKER]
        if not self.speech:
            raise ValueError("Transcript has no attributed speech.")
        self.teacher_cues = [cue for cue in self.speech if cue.speaker == TEACHER_CODE]
        self.minutes = max((transcript.end() - transcript.start()) / 60, MIN_MINUTES)

    def compute(self) -> InteractionMetrics:
        questions = self._teacher_questions()
        return InteractionMetrics(
            minutes=self.minutes,
            teacher_talk_share=self._teacher_talk_share(),
            turn_switches_per_min=self._turn_switches() / self.minutes,
            teacher_questions_per_min=len(questions) / self.minutes,
            named_question_share=self._named_question_share(questions),
            media_minutes=self._media_minutes(),
            long_gaps=self._long_gaps(),
        )

    def _teacher_talk_share(self) -> float:
        teacher_words = sum(cue.words for cue in self.teacher_cues)
        all_words = sum(cue.words for cue in self.speech)
        return teacher_words / max(all_words, 1)

    def _turn_switches(self) -> int:
        """Times the speaker changes between teacher and non-teacher."""
        switches = 0
        for previous, current in zip(self.speech, self.speech[1:]):
            if (previous.speaker == TEACHER_CODE) != (current.speaker == TEACHER_CODE):
                switches += 1
        return switches

    def _teacher_questions(self) -> list[Cue]:
        return [cue for cue in self.teacher_cues if "?" in cue.text]

    @staticmethod
    def _named_question_share(questions: list[Cue]) -> float:
        if not questions:
            return 0.0
        named = sum(1 for cue in questions if NAMED_PERSON.search(cue.text))
        return named / len(questions)

    def _media_minutes(self) -> float:
        media_seconds = sum(cue.end - cue.start for cue in self.transcript.cues if cue.media)
        return media_seconds / 60

    def _long_gaps(self) -> int:
        gaps = 0
        for previous, current in zip(self.speech, self.speech[1:]):
            if current.start - previous.end > config.LONG_GAP_S:
                gaps += 1
        return gaps
