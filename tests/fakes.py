"""Shared synthetic data and a fake Claude client for the llm tests (no network, no cost)."""

from types import SimpleNamespace

import httpx2

from classlens import config
from classlens.llm.schema import CriterionAssessment, Evidence, Judgement, Point
from classlens.metrics import InteractionAnalyzer
from classlens.models import Cue, PseudonymisedTranscript, QualityLevel, Transcript, TranscriptQuality

CUES = [
    Cue(0, 4, "T", "Hello S1, how was your tournament?"),
    Cue(5, 8, "S1", "I won two games ma'am!"),
    Cue(9, 12, "T", "Wonderful."),
    Cue(13, 20, "T", "Today we learn the fork."),
    Cue(30, 400, "T", "video narration", media=True),
    Cue(900, 905, "T", "S2, which piece can fork the king and rook?"),
    Cue(906, 909, "S2", "The knight!"),
    Cue(3500, 3530, "T", "For homework solve puzzles 1 to 5. Bye everyone!"),
]
CLEAN = PseudonymisedTranscript(Transcript(CUES), frozenset({"arjun", "tara"}))
METRICS = InteractionAnalyzer(CLEAN.transcript).compute()
QUALITY = TranscriptQuality(0.95, 90, 0.0, QualityLevel.GOOD)
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def judgement(**changes) -> Judgement:
    base = dict(
        criteria=[
            CriterionAssessment(
                criterion_id="C1", assessed=True, score=4, rationale="Warm start.",
                evidence=[Evidence(timestamp="00:00", quote="how was your tournament",
                                   observation="Personal chat", polarity="positive")],
            ),
            CriterionAssessment(
                criterion_id="C5", assessed=True, score=4, rationale="Specific homework.",
                evidence=[Evidence(timestamp="58:20", quote="For homework solve puzzles 1 to 5",
                                   observation="Set homework", polarity="positive")],
            ),
        ],
        strengths=[Point(criterion_id="C1", timestamp="00:00", text="Asks about the tournament")],
        improvements=[Point(criterion_id="C2", timestamp="15:01", text="Involve S1 in the fork puzzle")],
        holistic_grade="Good",
        transcript_quality="good",
        summary="Warm, structured class.",
    )
    return Judgement(**(base | changes))


def response(parsed, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=500, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, model=config.MODEL, usage=usage)


class FakeClient:
    """Stands in for anthropic.Anthropic(); returns or raises the given outcomes in order."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
