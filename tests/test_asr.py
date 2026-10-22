"""Transcriber with a fake Whisper model (no model download, no real audio)."""

from types import SimpleNamespace

import numpy as np

from classlens import config
from classlens.asr import SAMPLE_RATE, Transcriber
from classlens.models import UNKNOWN_SPEAKER


class FakeWhisper:
    """Returns the same segments for every window and records what it was given."""

    def __init__(self, segments):
        self.segments = segments
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((len(audio), options))
        return iter(self.segments), SimpleNamespace(language="en")


def segment(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


def test_transcribe_audio_in_windows(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_WINDOW_S", 10)
    model = FakeWhisper([segment(1.0, 2.0, " Hello everyone"), segment(3.0, 3.5, "  "), segment(4.0, 6.5, " Your move?")])
    transcript = Transcriber(model).transcribe_audio(np.zeros(25 * SAMPLE_RATE, dtype=np.float32))

    assert [samples / SAMPLE_RATE for samples, _ in model.calls] == [10, 10, 5]  # 25 s → 10 + 10 + 5
    assert all(options["vad_filter"] for _, options in model.calls)
    assert [(cue.start, cue.end, cue.speaker, cue.text) for cue in transcript.cues[:3]] == [
        (1.0, 2.0, UNKNOWN_SPEAKER, "Hello everyone"),
        (4.0, 6.5, UNKNOWN_SPEAKER, "Your move?"),
        (11.0, 12.0, UNKNOWN_SPEAKER, "Hello everyone"),  # second window starts at 10 s
    ]
    assert len(transcript.cues) == 6  # empty segments dropped
