"""PromptBuilder and merge_lines."""

import pytest

from classlens.llm.prompt import PromptBuilder, merge_lines
from classlens.models import Cue, PseudonymisedTranscript, Transcript
from classlens.privacy import PrivacyError
from tests.fakes import CLEAN, CUES, METRICS, QUALITY


def build(clean=CLEAN, findings=None):
    return PromptBuilder(findings).build(clean, METRICS, QUALITY, 3600)


def test_merge_lines_joins_same_speaker_and_media_runs():
    lines = merge_lines(Transcript(CUES))
    assert [(line.speaker, line.media) for line in lines] == [
        ("T", False), ("S1", False), ("T", False), ("T", True), ("T", False), ("S2", False), ("T", False),
    ]
    assert lines[2].text == "Wonderful. Today we learn the fork."


def test_merge_lines_splits_long_turns():
    cues = [Cue(0, 30, "T", "first"), Cue(31, 70, "T", "second")]  # 70 s > MAX_BLOCK_S
    assert len(merge_lines(Transcript(cues))) == 2


def test_payload_has_facts_phases_and_transcript():
    text = build(findings=["Teacher camera on 95% of teaching time."]).text
    for expected in (
        "RECORDING", "MEASURED INTERACTION", "VIDEO AND AUDIO FINDINGS",
        "=== OPENING ===", "=== MAIN ===", "=== CLOSING ===",
        "- Teacher camera on 95% of teaching time.",
        "[00:00] T: Hello S1", "(shared audio or video playing until 06:40)", "<transcript>",
    ):
        assert expected in text


def test_payload_without_findings_says_so():
    assert "- Not analysed for this run." in build().text


def test_payload_refuses_leftover_name():
    leaky = PseudonymisedTranscript(Transcript([*CUES, Cue(3540, 3545, "S1", "Bye Arjun")]), CLEAN.name_tokens)
    with pytest.raises(PrivacyError):
        build(clean=leaky)


def test_payload_refuses_name_in_findings():
    with pytest.raises(PrivacyError):
        build(findings=["Tara's camera was off"])
