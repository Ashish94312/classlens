"""Local-only check of the transcript layer on the real dataset (LLD §5.13).

Prints aggregate numbers per recording, never names or transcript text.
Usage: .venv/bin/python -m scripts.inspect_transcripts "<dataset dir>"
"""

import re
import sys
from pathlib import Path

from classlens.privacy import NameGuard, PrivacyError
from scripts.dataset import PreparedRecording, iter_recordings, prepare

DICTIONARY = Path("/usr/share/dict/words")
SPOKEN_NAME_CODE = re.compile(r"\bN\d+\b")
HEADER = (
    f"{'recording':22} {'min':>4} {'qual':>7} {'cov':>4} {'wpm':>4} {'amb':>3} {'T%':>3} {'sw/m':>5} {'Q/m':>4} {'nQ%':>3} "
    f"{'med':>4} {'gap':>3} {'N':>3} guard"
)


def guard_status(prepared: PreparedRecording) -> str:
    text = " ".join(f"{cue.speaker} {cue.text}" for cue in prepared.clean.transcript.cues)
    try:
        NameGuard(prepared.clean.name_tokens).check(text)
    except PrivacyError:
        return "LEAK"
    return "ok"


def row(prepared: PreparedRecording) -> str:
    m, q = prepared.metrics, prepared.quality
    minutes = (prepared.duration_s or m.minutes * 60) / 60
    spoken_names = set()
    for cue in prepared.clean.transcript.cues:
        spoken_names.update(SPOKEN_NAME_CODE.findall(cue.text))
    return (
        f"{prepared.recording.name:22} {minutes:4.0f} {q.level:>7} {q.coverage or 0:4.2f} "
        f"{q.words_per_min:4.0f} {'Y' if prepared.teacher.ambiguous else '-':>3} "
        f"{100 * m.teacher_talk_share:3.0f} {m.turn_switches_per_min:5.1f} "
        f"{m.teacher_questions_per_min:4.1f} {100 * m.named_question_share:3.0f} "
        f"{m.media_minutes:4.1f} {m.long_gaps:3} {len(spoken_names):3} "
        f"{guard_status(prepared)}"
    )


def main(dataset: Path) -> None:
    common_words = set()
    if DICTIONARY.exists():
        common_words = {word for word in DICTIONARY.read_text().split() if word.islower()}
    suspicious: set[str] = set()

    print(HEADER)
    for recording in iter_recordings(dataset):
        prepared = prepare(recording)
        suspicious |= prepared.clean.name_tokens & common_words
        print(row(prepared))
    # Count only: the system dictionary also contains some first names, so never print the words.
    print(f"\nDictionary words treated as names (possible false positives): {len(suspicious)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
