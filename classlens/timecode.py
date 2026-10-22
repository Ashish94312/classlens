"""Conversions between seconds and the "mm:ss" / "h:mm:ss" timestamps shown to the model."""

import re

# "12:31", "[12:31]", "1:02:05" — the first timestamp found in the text
TIMESTAMP = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def format_time(seconds: float) -> str:
    """65 → "01:05"; 3725 → "1:02:05"."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def parse_time(text: str) -> float | None:
    """"[01:05]" → 65; "1:02:05" → 3725; None when the text has no timestamp."""
    match = TIMESTAMP.search(text)
    if match is None:
        return None
    first, second, third = match.groups()
    if third is None:
        return int(first) * 60 + int(second)
    return int(first) * 3600 + int(second) * 60 + int(third)
