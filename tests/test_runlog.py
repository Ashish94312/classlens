import json
from types import SimpleNamespace

import pytest

from classlens.runlog import RunLog, estimate_cost, peak_memory_mb


def test_estimate_cost_uses_all_token_kinds():
    usage = SimpleNamespace(
        input_tokens=1_000_000, output_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000,
    )
    assert estimate_cost(usage) == pytest.approx(4.0 + 20.0 + 5.0 + 0.20)


def test_estimate_cost_tolerates_missing_cache_fields():
    assert estimate_cost(SimpleNamespace(input_tokens=1_000_000, output_tokens=0)) == pytest.approx(4.0)


def test_record_appends_json_lines_and_prints_them(tmp_path, capsys):
    log = RunLog(tmp_path / "logs" / "calls.jsonl")
    log.record("judge", "ok", {"input_tokens": 10})
    log.record("judge", "refusal", {})
    lines = [json.loads(line) for line in (tmp_path / "logs" / "calls.jsonl").read_text().splitlines()]
    assert [(line["purpose"], line["outcome"]) for line in lines] == [("judge", "ok"), ("judge", "refusal")]
    assert lines[0]["input_tokens"] == 10 and "ts" in lines[0]
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == lines  # for the Cloud log view


def test_peak_memory_is_a_plausible_size():
    assert 1 < peak_memory_mb() < 100_000
