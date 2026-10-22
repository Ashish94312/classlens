"""RoleLabeller with a fake client: request text, label mapping, name guard."""

import pytest

from classlens import config
from classlens.llm.roles import RoleLabeller
from classlens.llm.schema import RoleLabels
from classlens.models import STUDENT_CODE, TEACHER_CODE, UNKNOWN_SPEAKER, Cue, PseudonymisedTranscript, Transcript
from classlens.privacy import PrivacyError
from classlens.runlog import RunLog
from tests.fakes import FakeClient, response

LINES = [
    Cue(0, 4, UNKNOWN_SPEAKER, "Hello N1, how was your tournament?"),
    Cue(5, 8, UNKNOWN_SPEAKER, "I won two games ma'am!"),
    Cue(9, 40, UNKNOWN_SPEAKER, "In this video we will learn the fork."),
    Cue(41, 45, UNKNOWN_SPEAKER, "So which piece can fork the king?"),
]
CLEAN = PseudonymisedTranscript(Transcript(LINES), frozenset({"tara"}))


def label(client, tmp_path, clean=CLEAN):
    return RoleLabeller(client, RunLog(tmp_path / "ai_calls.jsonl")).label(clean)


def test_lines_not_listed_are_the_teacher(tmp_path):
    client = FakeClient(response(RoleLabels(student_lines=[2, 99], media_lines=[3])))
    result = label(client, tmp_path)

    assert [(cue.speaker, cue.media) for cue in result.transcript.cues] == [
        (TEACHER_CODE, False), (STUDENT_CODE, False), (TEACHER_CODE, True), (TEACHER_CODE, False),
    ]  # line 99 doesn't exist and is ignored
    assert [cue.text for cue in result.transcript.cues] == [cue.text for cue in LINES]
    assert result.name_tokens == CLEAN.name_tokens


def test_request_numbers_lines_and_uses_the_roles_prompt(tmp_path):
    client = FakeClient(response(RoleLabels(student_lines=[], media_lines=[])))
    label(client, tmp_path)
    request = client.calls[0]
    assert request["output_format"] is RoleLabels
    assert request["output_config"] == {"effort": config.ROLES_EFFORT}
    assert "2 [00:05] I won two games ma'am!" in request["messages"][0]["content"]
    assert "Every line you don't list counts as the teacher's" in request["system"][0]["text"]


def test_name_left_in_text_blocks_the_call(tmp_path):
    leaky = PseudonymisedTranscript(Transcript([Cue(0, 2, UNKNOWN_SPEAKER, "Well done Tara")]), frozenset({"tara"}))
    client = FakeClient()
    with pytest.raises(PrivacyError):
        label(client, tmp_path, leaky)
    assert client.calls == []
