"""Scorer: weighted score, bands, unassessed criteria, provisional grades, video scores and gates."""

import pytest

from classlens.llm.schema import CriterionAssessment
from classlens.models import VideoFindings
from classlens.scoring import Scorer, best_allowed, presence_score, technical_score
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


def video(**changes) -> VideoFindings:
    """A clean class: camera on, face visible and well lit, no freezes."""
    base = dict(frames=120, screen_share=0.5, gallery=0.0, camera_off=0.0, face_visible=1.0, low_light=0.0,
                blurry=0.0, frozen=0.0, camera_off_at=[], no_face_at=[], frozen_at=[])
    return VideoFindings(**(base | changes))


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, 4),
    ({"camera_off": 0.1}, 3),
    ({"camera_off": 0.4}, 2),
    ({"face_visible": 0.5}, 3),
    ({"face_visible": 0.1, "low_light": 0.5}, 1),
    ({"face_visible": None, "low_light": None}, 4),  # no camera-on frame: only the camera-off share counts
    ({"gallery": 0.8}, None),
])
def test_presence_score_from_video(changes, expected):
    assert presence_score(video(**changes)) == expected


def test_technical_score_from_video():
    assert technical_score(video()) == 4
    assert technical_score(video(frozen=0.2, blurry=0.5)) == 2
    assert technical_score(video(frozen=None)) is None


def test_video_sets_c6_and_blends_c7():
    scores = Scorer.criterion_scores(judgement(criteria=criteria({"C6": 4, "C7": 2})), video(camera_off=0.1))
    assert scores == {"C6": 3.0, "C7": 3.0}  # C6: the lower of 4 and 3; C7: mean of 2 and 4
    scores = Scorer.criterion_scores(judgement(criteria=criteria({"C6": None, "C7": None})), video())
    assert scores == {"C6": 4.0, "C7": 4.0}  # video alone when Claude could not assess them


def test_gates_cap_the_grade():
    all_four = judgement(criteria=criteria({cid: 4 for cid in ALL}))
    one = Scorer().grade(all_four, video(face_visible=0.1))
    assert one.grade == "Average" and len(one.flags) == 1 and "10%" in one.flags[0]
    two = Scorer().grade(all_four, video(face_visible=0.1, camera_off=0.5))
    assert two.grade == "Poor" and len(two.flags) == 2
    assert Scorer().grade(all_four, video(face_visible=0.1, gallery=0.9)).flags == ()  # gallery: not judged
    assert best_allowed(0) == "Excellent" and best_allowed(1) == "Average" and best_allowed(3) == "Poor"
