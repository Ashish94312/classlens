"""Local-only: run the full pipeline on the labelled recordings and compare each grade with the
label (HLD §6.3, §9.6; LLD §5.13). Two Claude calls per recording (about $0.10–0.25).
Prints grades and aggregates only, never names or transcript text.

Usage: .venv/bin/python -m scripts.evaluate "<dataset dir>" [--cache DIR] [keys...]
  --cache DIR: keep Whisper transcripts in DIR (local, never committed) so reruns skip speech-to-text
"""

import json
import pickle
import sys
import tempfile
from pathlib import Path

from classlens import config
from classlens.asr import Transcriber
from classlens.ingest import run_id
from classlens.llm.judge import ClaudeJudge
from classlens.llm.roles import RoleLabeller
from classlens.pipeline import AssessmentPipeline
from classlens.runlog import RunLog
from scripts.dataset import iter_recordings

# Dataset folder → expected grade. The brief has four grades; weak and known-quality-issue classes are Poor.
LABEL_TO_GRADE = {"excellent": "Excellent", "good": "Good", "average": "Average", "weak": "Poor", "quality issue": "Poor"}
GRADES = [grade for _, grade in reversed(config.GRADE_BANDS)]  # Poor … Excellent
REDACT_LIST = config.ROOT / "redact_names.txt"


class CachedTranscriber:
    """Whisper with an optional local cache keyed by run id (content hash, not the file name)."""

    def __init__(self, folder: Path | None):
        self.folder = folder
        self.inner = Transcriber()

    def transcribe(self, path: Path):
        if self.folder is None:
            return self.inner.transcribe(path)
        cached = self.folder / f"{run_id(path)}.pkl"
        if not cached.exists():
            cached.write_bytes(pickle.dumps(self.inner.transcribe(path)))
        return pickle.loads(cached.read_bytes())


def confusion(rows: list[tuple[str, str]]) -> str:
    """Rows: expected grade; columns: computed grade."""
    lines = ["expected \\ got " + " ".join(f"{grade:>9}" for grade in GRADES)]
    for expected in GRADES:
        counts = [sum(1 for e, g in rows if e == expected and g == got) for got in GRADES]
        lines.append(f"{expected:>14} " + " ".join(f"{count:>9}" for count in counts))
    return "\n".join(lines)


def main(dataset: Path, keys: set[str], cache: Path | None) -> None:
    config.load_env_file()
    known_names = frozenset()
    if REDACT_LIST.exists():  # replace every known real name, even those the rules miss, before any Claude call
        known_names = frozenset(line.strip().casefold() for line in REDACT_LIST.read_text().splitlines() if line.strip())
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        log = RunLog(Path(tmp) / "runs.jsonl")
        pipeline = AssessmentPipeline(CachedTranscriber(cache), RoleLabeller(log=log), ClaudeJudge(log=log), known_names)
        computed, holistic = [], []
        for recording in iter_recordings(dataset, keys):
            if recording.video_path is None:
                continue
            expected = LABEL_TO_GRADE.get(recording.label.lower())
            assessment = pipeline.run(recording.video_path, {})
            if assessment.grade is None:
                print(f"{recording.name:22} {expected or '-':>9}  no grade: {assessment.note}", flush=True)
                continue
            grade, judgement = assessment.grade, assessment.judge.judgement
            print(f"{recording.name:22} expected {expected or '-':>9}  got {grade.grade:>9} ({grade.score:5.1f}, "
                  f"assessed {grade.assessed_weight:.0%})  AI overall {judgement.holistic_grade:>9}  "
                  f"transcript {judgement.transcript_quality}", flush=True)
            if expected:
                computed.append((expected, grade.grade))
                holistic.append((expected, judgement.holistic_grade))

        calls = [json.loads(line) for line in log.path.read_text().splitlines()] if log.path.exists() else []
        cost = sum(call.get("cost_usd", 0) for call in calls)
    for name, rows in [("Rubric grade", computed), ("AI overall view", holistic)]:
        exact = sum(e == g for e, g in rows)
        near = sum(abs(GRADES.index(e) - GRADES.index(g)) <= 1 for e, g in rows)
        print(f"\n{name}: {exact}/{len(rows)} exact, {near}/{len(rows)} within one grade\n{confusion(rows)}")
    print(f"\nClaude cost for this run: ${cost:.2f}")


if __name__ == "__main__":
    args = sys.argv[2:]
    cache_dir = None
    if "--cache" in args:
        index = args.index("--cache")
        cache_dir = Path(args[index + 1])
        args = args[:index] + args[index + 2:]
    main(Path(sys.argv[1]), {key.lower() for key in args}, cache_dir)
