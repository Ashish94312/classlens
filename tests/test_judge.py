"""ClaudeJudge with a fake client: request shape, retries, failures, logging."""

import json

import anthropic
import httpx2
import pytest

from classlens import config
from classlens.llm.claude import AIUnavailable, load_prompt
from classlens.llm.judge import ClaudeJudge
from classlens.llm.prompt import PromptBuilder
from classlens.llm.schema import Judgement
from classlens.runlog import RunLog
from tests.fakes import CLEAN, METRICS, QUALITY, REQUEST, FakeClient, judgement, response

PAYLOAD = PromptBuilder().build(CLEAN, METRICS, QUALITY, 3600)


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "ai_calls.jsonl"


def judge(client, log_path):
    return ClaudeJudge(client, RunLog(log_path))


def test_sends_expected_request(log_path):
    client = FakeClient(response(judgement()))
    result = judge(client, log_path).assess(PAYLOAD)
    sent = client.calls[0]
    assert sent["model"] == config.MODEL and sent["output_config"] == {"effort": config.EFFORT}
    assert sent["output_format"] is Judgement and sent["fallbacks"] == "default"
    assert sent["betas"] == [config.FALLBACK_BETA]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["messages"] == [{"role": "user", "content": PAYLOAD.text}]
    assert result.judgement.holistic_grade == "Good" and result.trace["attempts"] == 1


def test_retries_truncated_answer_once(log_path):
    client = FakeClient(response(None, stop_reason="max_tokens"), response(judgement()))
    result = judge(client, log_path).assess(PAYLOAD)
    assert result.trace["attempts"] == 2 and result.trace["input_tokens"] == 2000


@pytest.mark.parametrize(
    ("outcomes", "message"),
    [
        ([response(None, stop_reason="refusal")], "declined"),
        ([ValueError("bad json"), ValueError("bad json")], "could not be read"),
        ([anthropic.APIConnectionError(request=REQUEST)], "Could not reach"),
        ([anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=REQUEST), body=None)], "rejected"),
        ([anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=REQUEST), body=None)], "rate-limited"),
        ([anthropic.InternalServerError("boom", response=httpx2.Response(500, request=REQUEST), body=None)], "(500)"),
    ],
)
def test_failures_become_ai_unavailable(outcomes, message, log_path):
    with pytest.raises(AIUnavailable, match=message):
        judge(FakeClient(*outcomes), log_path).assess(PAYLOAD)


def test_missing_api_key(monkeypatch, log_path):
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    with pytest.raises(AIUnavailable, match="No Claude API key"):
        judge(None, log_path).assess(PAYLOAD)


def test_logs_metadata_without_transcript_text(log_path):
    result = judge(FakeClient(response(judgement())), log_path).assess(PAYLOAD)
    assert result.trace["evidence_accepted"] == 2 and result.trace["evidence_rejected"] == 0
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["outcome"] == "ok" and record["prompt_version"] == config.PROMPT_VERSION
    assert "tournament" not in json.dumps(record)


def test_refusal_is_logged(log_path):
    with pytest.raises(AIUnavailable):
        judge(FakeClient(response(None, stop_reason="refusal")), log_path).assess(PAYLOAD)
    assert json.loads(log_path.read_text().splitlines()[-1])["outcome"] == "refusal"


def test_system_prompt_is_the_versioned_rubric():
    assert "C1 Opening and rapport" in load_prompt(config.PROMPT_VERSION)
