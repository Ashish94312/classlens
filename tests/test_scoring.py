"""Scorer: weighted score, bands, unassessed criteria, provisional grades."""

import pytest

from classlens.llm.schema import CriterionAssessment
from classlens.scoring import Scorer
from tests.fakes import judgement


def criteria(scores: dict) -> list[CriterionAssessment]:
    """criterion id → score (None = not assessed)."""
    return [
        CriterionAssessment(criterion_id=cid, assessed=score is not None, score=score, rationale="r", evidence=[])
        for cid, score in scores.items()
    ]


ALL = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


@pytest.mark.parametrize(("score", "grade"), [(4, "Excellent"), (3, "Good"), (2, "Poor"), (1, "Poor")])
def test_uniform_scores(score, grade):
    result = Scorer().grade(judgement(criteria=criteria({cid: score for cid in ALL})))
    assert result.grade == grade
    assert result.score == pytest.approx(100 * (score - 1) / 3, abs=0.1)
    assert result.assessed_weight == 1.0 and not result.provisional


def test_bands_between_levels():
    # C1 20, C2 25 at 4; the rest at 2 → (45×1 + 55×1/3) / 100 = 63.3 → Good
    result = Scorer().grade(judgement(criteria=criteria({"C1": 4, "C2": 4, "C3": 2, "C4": 2, "C5": 2, "C6": 2, "C7": 2})))
    assert result.score == pytest.approx(63.3, abs=0.1) and result.grade == "Good"
    # C1, C2 at 3; the rest at 2 → (45×2/3 + 55×1/3) / 100 = 48.3 → Average
    result = Scorer().grade(judgement(criteria=criteria({"C1": 3, "C2": 3, "C3": 2, "C4": 2, "C5": 2, "C6": 2, "C7": 2})))
    assert result.score == pytest.approx(48.3, abs=0.1) and result.grade == "Average"


def test_unassessed_criteria_do_not_count_against_the_teacher():
    result = Scorer().grade(judgement(criteria=criteria({"C1": None, "C2": 4, "C3": 4, "C4": 4, "C5": None, "C6": None, "C7": 4})))
    assert result.grade == "Excellent" and result.score == 100.0
    assert result.assessed_weight == 0.6 and not result.provisional  # 25 + 15 + 15 + 5 = 60 of 100


def test_too_little_assessed_is_provisional():
    result = Scorer().grade(judgement(criteria=criteria({"C2": 3, "C3": 3, "C1": None, "C4": None, "C5": None, "C6": None, "C7": None})))
    assert result.provisional and result.assessed_weight == 0.4 and result.grade == "Good"


def test_nothing_assessed():
    result = Scorer().grade(judgement(criteria=criteria({cid: None for cid in ALL})))
    assert result.provisional and result.assessed_weight == 0.0
