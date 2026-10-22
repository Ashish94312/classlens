"""Local-only: run the Claude judge on real recordings (LLD §5.13).

Prints aggregate numbers only. Full validated judgements go to eval/runs/ (git-ignored) for review.
Usage:
  .venv/bin/python -m scripts.try_judge "<dataset dir>" [--dry-run] [keys...]
  keys filter recordings, e.g. b491 b482 (default: all)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from classlens import config
from classlens.llm.claude import AIUnavailable
from classlens.llm.judge import ClaudeJudge, JudgeResult
from classlens.llm.prompt import PromptBuilder
from scripts.dataset import iter_recordings, prepare


def summary_line(name: str, result: JudgeResult) -> str:
    scores = " ".join(
        f"{c.criterion_id}={c.score if c.assessed else '-'}" for c in result.judgement.criteria
    )
    t = result.trace
    checked = t["evidence_accepted"] + t["evidence_rejected"]
    return (
        f"{name:20} {result.judgement.holistic_grade:9} {scores}  evidence {t['evidence_accepted']}/{checked}"
        f"  tq={result.judgement.transcript_quality:7} {t['input_tokens']}/{t['output_tokens']} tok"
        f"  ${t['cost_usd']:.3f}  {t['latency_s']:.0f}s"
    )


def main(dataset: Path, dry_run: bool, keys: set[str]) -> None:
    config.load_env_file()
    run_dir = config.ROOT / "eval" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    judge = ClaudeJudge()
    total_cost = 0.0

    for recording in iter_recordings(dataset, keys):
        prepared = prepare(recording)
        payload = PromptBuilder().build(prepared.clean, prepared.metrics, prepared.quality, prepared.duration_s)
        if dry_run:
            print(f"{recording.name:20} payload {len(payload.text):6} chars ≈ {len(payload.text) // 4:5} tokens, name guard ok")
            continue
        try:
            result = judge.assess(payload)
        except AIUnavailable as err:
            print(f"{recording.name:20} unavailable: {err}")
            continue

        total_cost += result.trace["cost_usd"]
        print(summary_line(recording.name, result))
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {"label": recording.label, "trace": result.trace, "judgement": result.judgement.model_dump()}
        (run_dir / f"{recording.label}-{recording.key}.json").write_text(json.dumps(record, indent=2))

    if not dry_run:
        print(f"\nTotal cost ≈ ${total_cost:.2f}; full results in {run_dir.relative_to(config.ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(Path(args[0]), "--dry-run" in args, {a.lower() for a in args[1:] if not a.startswith("--")})
