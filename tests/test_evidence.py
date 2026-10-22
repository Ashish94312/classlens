"""EvidenceValidator: only quotes found at the cited time survive."""

from classlens import config
from classlens.llm.evidence import EvidenceValidator
from classlens.llm.prompt import merge_lines
from classlens.llm.schema import CriterionAssessment, Evidence
from tests.fakes import CLEAN, judgement

LINES = merge_lines(CLEAN.transcript)


def evidence(timestamp, quote):
    return Evidence(timestamp=timestamp, quote=quote, observation="o", polarity="positive")


def test_keeps_grounded_evidence_only():
    raw = judgement(criteria=[
        CriterionAssessment(criterion_id="C2", assessed=True, score=3, rationale="r", evidence=[
            evidence("15:01", "which piece can fork the king, and rook"),  # punctuation differs: kept
            evidence("00:00", "which piece can fork the king"),  # wrong time: dropped
            evidence("15:01", "excellent explanation of pins"),  # made up: dropped
        ]),
    ])
    result = EvidenceValidator(LINES).validate(raw)
    assert result.counts["C2"] == (1, 2)


def test_completes_and_normalises_criteria():
    raw = judgement(criteria=[
        CriterionAssessment(criterion_id="C3", assessed=True, score=None, rationale="no score", evidence=[]),
        CriterionAssessment(criterion_id="C3", assessed=True, score=4, rationale="duplicate", evidence=[]),
    ])
    checked = EvidenceValidator(LINES).validate(raw).judgement
    by_id = {c.criterion_id: c for c in checked.criteria}
    assert [c.criterion_id for c in checked.criteria] == list(config.CRITERIA)
    assert not by_id["C3"].assessed and by_id["C3"].score is None  # first answer wins
    assert not by_id["C7"].assessed  # missing from the answer → not assessed


def test_points_need_a_transcript_line_at_their_time():
    raw = judgement()
    raw.improvements.append(raw.improvements[0].model_copy(update={"timestamp": "30:00"}))
    checked = EvidenceValidator(LINES).validate(raw).judgement
    assert len(checked.strengths) == 1 and len(checked.improvements) == 1


def test_evidence_inside_shared_media_is_rejected():
    raw = judgement(criteria=[
        CriterionAssessment(criterion_id="C4", assessed=True, score=3, rationale="r",
                            evidence=[evidence("03:00", "video narration")]),
    ])
    assert EvidenceValidator(LINES).validate(raw).counts["C4"] == (0, 1)
