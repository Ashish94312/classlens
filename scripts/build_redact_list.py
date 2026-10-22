"""Write the git-ignored redact_names.txt used by the pre-commit guard and the AI-log export
(LLD §5.13) and as the reference for leak checks. Collects, from every transcript, display-name
tokens and names said in class that Zoom capitalises mid-sentence or calls out ("Ishaan, …") at
least once, and, if pdftotext
is available, teacher names from the reviewer feedback PDF. Precision matters here: a common word
in the list would block ordinary commits. Prints only a count.

Usage: .venv/bin/python -m scripts.build_redact_list "<dataset dir>"
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from classlens.privacy import NOT_NAMES, Pseudonymiser, display_name_tokens
from scripts.dataset import iter_recordings, prepare

DICTIONARY = Path("/usr/share/dict/words")
OUTPUT = Path("redact_names.txt")
# Feedback entries look like "B123 (dd/mm/yyyy) FIRST LAST -------comments" → "FIRST LAST"
FEEDBACK_NAME = re.compile(r"\)\s*([A-Za-z][A-Za-z .]+?)\s*-{3,}")
INFLECTIONS = ("s", "es", "ed", "d", "ing", "er", "ly")  # "lines" → "line", "moved" → "move"
# A name called out at the start of a sentence: "Ishaan, your move"
VOCATIVE = re.compile(r"(?:^|[.?!]\s+)([A-Z][a-z]{2,}),\s")


def feedback_names(pdf: Path) -> set[str]:
    if not pdf.exists() or shutil.which("pdftotext") is None:
        return set()
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    tokens = set()
    for label in FEEDBACK_NAME.findall(text):
        tokens.update(display_name_tokens(label))
    return tokens


def is_common_word(token: str, common: set[str]) -> bool:
    """In the dictionary, or an inflection of a word in it: the system list has few plurals
    ("line" but not "lines")."""
    if token in common:
        return True
    for suffix in INFLECTIONS:
        if token.endswith(suffix) and token[: -len(suffix)] in common:
            return True
    return False


def main(dataset: Path) -> None:
    tokens: set[str] = set()
    for recording in iter_recordings(dataset):
        prepared = prepare(recording)
        for cue in prepared.transcript.cues:
            tokens.update(display_name_tokens(cue.speaker))
        mid_sentence, _, _ = Pseudonymiser._word_counts(prepared.transcript)
        called_out = {match.casefold() for cue in prepared.transcript.cues for match in VOCATIVE.findall(cue.text)}
        tokens |= prepared.clean.name_tokens & (set(mid_sentence) | called_out)
    tokens |= feedback_names(dataset / "feedbacks.pdf")

    # Common words would block ordinary commits and raise false leak alarms; they are not names.
    tokens -= NOT_NAMES
    if DICTIONARY.exists():
        common = {word for word in DICTIONARY.read_text().split() if word.islower()}
        tokens = {token for token in tokens if not is_common_word(token, common)}
    OUTPUT.write_text("\n".join(sorted(tokens)) + "\n", encoding="utf-8")
    print(f"Wrote {len(tokens)} name tokens to {OUTPUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
