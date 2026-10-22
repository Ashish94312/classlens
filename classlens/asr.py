"""Speech-to-text on this server (HLD §9.1, LLD §5.16). Audio never leaves the machine."""

from pathlib import Path

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

from classlens import config
from classlens.models import UNKNOWN_SPEAKER, Cue, Transcript

SAMPLE_RATE = 16000  # Whisper's input: 16 kHz mono


class Transcriber:
    """Local Whisper (faster-whisper, CPU, int8): recording → Transcript of unlabelled lines.

    Whisper gives timed text but no speakers, so every cue gets UNKNOWN_SPEAKER; roles are
    labelled later on the pseudonymised text."""

    def __init__(self, model=None):
        self._model = model  # injected in tests; loaded on first use otherwise (downloaded once)

    def transcribe(self, media_path: Path) -> Transcript:
        """Decode the audio once, straight from the video file."""
        return self.transcribe_audio(decode_audio(str(media_path), sampling_rate=SAMPLE_RATE))

    def transcribe_audio(self, audio) -> Transcript:
        """Transcribe WHISPER_WINDOW_S pieces one after another. Whisper builds its input features
        for everything it is given at once, so a whole class in one call peaks above 2 GB."""
        window = config.WHISPER_WINDOW_S * SAMPLE_RATE
        cues = []
        for offset in range(0, len(audio), window):
            cues.extend(self._transcribe_window(audio[offset : offset + window], offset / SAMPLE_RATE))
        return Transcript(cues)

    def _transcribe_window(self, audio, start_s: float) -> list[Cue]:
        """VAD skips long silences; timestamps are shifted from the window to the recording."""
        segments, _info = self._get_model().transcribe(audio, beam_size=config.WHISPER_BEAM_SIZE, vad_filter=True)
        cues = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                cues.append(Cue(start_s + segment.start, start_s + segment.end, UNKNOWN_SPEAKER, text))
        return cues

    def _get_model(self):
        if self._model is None:
            self._model = WhisperModel(
                config.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=config.WHISPER_THREADS
            )
        return self._model
