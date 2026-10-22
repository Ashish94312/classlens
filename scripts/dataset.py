"""Local-only helpers for the confidential dataset (LLD §5.13). Never imported by the app."""

import re
from dataclasses import dataclass
from pathlib import Path

from classlens.ingest import probe
from classlens.metrics import InteractionAnalyzer
from classlens.models import (
    InteractionMetrics,
    PseudonymisedTranscript,
    TeacherGuess,
    Transcript,
    TranscriptQuality,
)
from classlens.privacy import Pseudonymiser
from classlens.transcript import TranscriptAnalyzer, TranscriptParser

# Batch id or language in a file name: "B491 Beginner Part - 2026-06-29.mp4" → "B491"
RECORDING_KEY = re.compile(r"B\d{3}|english|malayalam", re.I)


@dataclass(frozen=True)
class Recording:
    label: str  # quality folder, e.g. "excellent"
    key: str  # e.g. "b491"
    transcript_path: Path
    video_path: Path | None

    @property
    def name(self) -> str:
        """Short display name without personal data, e.g. "excellent/b491"."""
        return f"{self.label[:9]}/{self.key}"


@dataclass(frozen=True)
class PreparedRecording:
    """Output of the transcript layer for one recording, as the app will compute it."""

    recording: Recording
    duration_s: float | None
    transcript: Transcript
    teacher: TeacherGuess
    clean: PseudonymisedTranscript
    quality: TranscriptQuality
    metrics: InteractionMetrics


def recording_key(path: Path) -> str:
    match = RECORDING_KEY.search(path.name)
    return match.group(0).lower() if match else path.stem


def iter_recordings(dataset: Path, keys: set[str] | None = None):
    """Yield a Recording for every transcript in <dataset>/<label>/ with its matching video,
    optionally filtered by key."""
    for transcript_path in sorted(dataset.glob("*/*.vtt")):
        key = recording_key(transcript_path)
        if keys and key not in keys:
            continue
        videos = [video for video in transcript_path.parent.glob("*.mp4") if recording_key(video) == key]
        yield Recording(
            label=transcript_path.parent.name.strip(),
            key=key,
            transcript_path=transcript_path,
            video_path=videos[0] if videos else None,
        )


def prepare(recording: Recording) -> PreparedRecording:
    """Run the transcript layer: parse → teacher → pseudonymise → quality, metrics."""
    duration_s = probe(recording.video_path).duration_s if recording.video_path else None
    raw = recording.transcript_path.read_text(encoding="utf-8", errors="replace")
    transcript = TranscriptParser().parse(raw)
    analyzer = TranscriptAnalyzer(transcript)
    teacher = analyzer.teacher()
    clean = Pseudonymiser(teacher.speaker).apply(transcript)
    return PreparedRecording(
        recording=recording,
        duration_s=duration_s,
        transcript=transcript,
        teacher=teacher,
        clean=clean,
        quality=analyzer.quality(duration_s),
        metrics=InteractionAnalyzer(clean.transcript).compute(),
    )
