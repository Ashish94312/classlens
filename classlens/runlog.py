"""Runtime log (HLD §13, LLD §5.11): one JSON line per analysis and per AI call.

Numbers and labels only: never transcript text, names or file names. Each line is also printed,
because on Streamlit Community Cloud the app's output ("Manage app → Logs") outlives restarts and
files on the server don't.
"""

import json
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path

from classlens import config


def estimate_cost(usage) -> float:
    """Estimated USD cost of one call, from the API's usage block and PRICE_PER_MTOK."""
    price = config.PRICE_PER_MTOK
    tokens = {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_write": getattr(usage, "cache_creation_input_tokens", None) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", None) or 0,
    }
    total = 0.0
    for kind, count in tokens.items():
        total += count * price[kind]
    return total / 1_000_000


def peak_memory_mb() -> float:
    """Highest memory use of this process so far."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024  # bytes on macOS, KiB on Linux


class RunLog:
    """Append-only JSON-lines file."""

    def __init__(self, path: Path | None = None):
        self.path = path  # None → config.RUN_LOG_PATH, read at write time

    def record(self, purpose: str, outcome: str, fields: dict) -> None:
        """purpose: "analysis", "roles", "judge"; outcome: "ok", "rejected", "error", "refusal"…"""
        path = self.path or config.RUN_LOG_PATH
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "purpose": purpose,
            "outcome": outcome,
            **fields,
        }
        line = json.dumps(entry)
        print(line, flush=True)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as log:
                log.write(line + "\n")
        except OSError:  # a read-only host still has the printed line
            pass
