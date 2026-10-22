"""Local-only: time Whisper on labelled recordings and compare its words with the Zoom VTT (LLD §5.13).

Prints aggregates only, never transcript text. Runs with config.WHISPER_THREADS, like the host.
Usage: .venv/bin/python -m scripts.try_asr "<dataset dir>" [keys...]
"""

import re
import sys
import time
from collections import Counter
from pathlib import Path

from classlens.asr import Transcriber
from classlens.ingest import probe
from classlens.models import Transcript
from classlens.runlog import peak_memory_mb
from classlens.transcript import TranscriptParser
from scripts.dataset import iter_recordings

WORD = re.compile(r"[\w']+")
HEADER = f"{'recording':22} {'min':>4} {'asr s':>6} {'x real':>6} {'vtt w':>6} {'asr w':>6} {'recall':>6} {'peak MB':>7}"


def words(transcript: Transcript) -> list[str]:
    found = []
    for cue in transcript.speech():
        found.extend(WORD.findall(cue.text.lower()))
    return found


def word_recall(reference: list[str], hypothesis: list[str]) -> float:
    """Share of the reference words (counted with repeats) that also appear in the hypothesis."""
    if not reference:
        return 0.0
    shared = Counter(reference) & Counter(hypothesis)
    return sum(shared.values()) / len(reference)


def main(dataset: Path, keys: set[str]) -> None:
    transcriber = Transcriber()
    print(HEADER)
    for recording in iter_recordings(dataset, keys):
        if recording.video_path is None:
            continue
        minutes = probe(recording.video_path).duration_s / 60
        started = time.perf_counter()
        asr = transcriber.transcribe(recording.video_path)
        seconds = time.perf_counter() - started
        raw = recording.transcript_path.read_text(encoding="utf-8", errors="replace")
        vtt_words, asr_words = words(TranscriptParser().parse(raw)), words(asr)
        print(
            f"{recording.name:22} {minutes:4.0f} {seconds:6.0f} {minutes * 60 / seconds:6.1f} "
            f"{len(vtt_words):6} {len(asr_words):6} {word_recall(vtt_words, asr_words):6.2f} {peak_memory_mb():7.0f}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), {key.lower() for key in sys.argv[2:]})
