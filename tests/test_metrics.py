"""InteractionAnalyzer on a synthetic pseudonymised transcript."""

import pytest

from classlens.metrics import InteractionAnalyzer
from classlens.models import Cue, Transcript

CLASS = [
    Cue(0, 5, "T", "Hello everyone, how are you?"),
    Cue(6, 8, "S1", "Good ma'am"),
    Cue(9, 15, "T", "S1, which piece can fork the king?"),
    Cue(16, 18, "S1", "The knight"),
    Cue(19, 25, "T", "Very good! S2, what about you?"),
    Cue(26, 28, "S2", "I agree"),
    Cue(30, 90, "T", "Let us watch a video", media=True),
    Cue(91, 120, "T", "Now everyone try this puzzle"),
]


def compute(cues):
    return InteractionAnalyzer(Transcript(cues)).compute()


def test_metrics_on_small_class():
    m = compute(CLASS)
    assert m.minutes == pytest.approx(2.0)
    assert m.teacher_talk_share == pytest.approx(23 / 29)
    assert m.turn_switches_per_min == pytest.approx(6 / 2)  # T S1 T S1 T S2 T
    assert m.teacher_questions_per_min == pytest.approx(3 / 2)
    assert m.named_question_share == pytest.approx(2 / 3)
    assert m.media_minutes == pytest.approx(1.0)
    assert m.long_gaps == 1  # 28 s → 91 s around the shared video


def test_student_code_from_speech_to_text_counts_as_student():
    m = compute([Cue(0, 30, "T", "N1, your move? Think first"), Cue(31, 32, "S", "e4"), Cue(33, 60, "T", "Good")])
    assert m.teacher_talk_share == pytest.approx(6 / 7)  # 5 + 1 teacher words, 1 student word
    assert m.turn_switches_per_min == pytest.approx(2 / 1)
    assert m.named_question_share == 1.0


def test_requires_attributed_speech():
    with pytest.raises(ValueError):
        compute([Cue(0, 5, "Unknown", "hello")])
