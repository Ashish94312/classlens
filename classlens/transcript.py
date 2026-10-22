"""Transcript reading and structure (LLD §5.4).

TranscriptParser turns WebVTT/SRT text into a Transcript.
TranscriptAnalyzer answers questions about it: who is the teacher and how good is the text.
"""

import re

from classlens import config
from classlens.models import (
    UNKNOWN_SPEAKER,
    Cue,
    QualityLevel,
    TeacherGuess,
    Transcript,
    TranscriptQuality,
)

# "00:01:02.500" (VTT) or "00:01:02,500" (SRT); hours optional
_STAMP = r"(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}"
# "00:01:02.500 --> 00:01:04.000 align:start" → the two timestamps
TIMING = re.compile(rf"({_STAMP})\s*-->\s*({_STAMP})")
# "<v Priya Rao>Hello" → "Priya Rao"
VOICE_TAG = re.compile(r"^<v(?:\.[^\s>]*)?\s+([^>]+)>")
# "<i>", "</v>" and any other markup tag
ANY_TAG = re.compile(r"<[^>]+>")
# Zoom style "Priya Rao: Hello" → ("Priya Rao", "Hello"); needs a space after the colon, so "10:30 …" is not a speaker
SPEAKER_PREFIX = re.compile(r"^([^:]{1,40}?):\s+(.+)$")
# Blank line between cue blocks
BLOCK_SEPARATOR = re.compile(r"\n\s*\n")
# Zoom labels computer audio the host shares (e.g. a video) as "Audio shared by <host>"
MEDIA_PREFIX = "audio shared by "


class TranscriptParser:
    """Turns WebVTT or SRT text into a Transcript. Tolerates BOMs, cue settings, voice tags and
    missing speaker labels."""

    def parse(self, raw: str) -> Transcript:
        cues = []
        for block in self._split_blocks(self._normalise(raw)):
            cue = self._parse_block(block)
            if cue is not None:
                cues.append(cue)
        cues.sort(key=lambda cue: cue.start)
        return Transcript(cues)

    @staticmethod
    def _normalise(raw: str) -> str:
        return raw.lstrip("﻿").replace("\r\n", "\n")

    @staticmethod
    def _split_blocks(text: str) -> list[str]:
        return BLOCK_SEPARATOR.split(text)

    def _parse_block(self, block: str) -> Cue | None:
        """One cue block → Cue. Blocks without a timing line (header, NOTE, STYLE) → None."""
        lines = block.strip().split("\n")
        for index, line in enumerate(lines):
            timing = self._parse_timing(line)
            if timing is not None:
                break
        else:
            return None

        start, end = timing
        text = " ".join(line.strip() for line in lines[index + 1 :]).strip()
        speaker, text, media = self._extract_speaker(text)
        if not text:
            return None
        return Cue(start, end, speaker, text, media)

    @staticmethod
    def _parse_timing(line: str) -> tuple[float, float] | None:
        match = TIMING.search(line)
        if match is None:
            return None
        return _to_seconds(match.group(1)), _to_seconds(match.group(2))

    @staticmethod
    def _extract_speaker(text: str) -> tuple[str, str, bool]:
        """Return (speaker, text without the label, is_shared_media)."""
        speaker = UNKNOWN_SPEAKER
        voice = VOICE_TAG.match(text)
        if voice:
            speaker = voice.group(1).strip()
        text = ANY_TAG.sub("", text).strip()

        if speaker == UNKNOWN_SPEAKER:
            prefix = SPEAKER_PREFIX.match(text)
            if prefix:
                speaker, text = prefix.group(1).strip(), prefix.group(2).strip()

        media = speaker.lower().startswith(MEDIA_PREFIX)
        if media:
            speaker = speaker[len(MEDIA_PREFIX) :].strip()
        return speaker, text, media


class TranscriptAnalyzer:
    """Structure of a transcript: teacher and text quality."""

    def __init__(self, transcript: Transcript):
        self.transcript = transcript
        self.speech = transcript.speech()

    def teacher(self) -> TeacherGuess:
        """Speaker with most words; the host (who shares audio) wins a near tie (HLD §5 step 2)."""
        words = self._words_by_speaker()
        if not words:
            return TeacherGuess(UNKNOWN_SPEAKER, ambiguous=True)
        ranked = sorted(words.items(), key=lambda item: item[1], reverse=True)[:2]
        if len(ranked) == 1:
            return TeacherGuess(ranked[0][0], ambiguous=False)

        (first, first_words), (second, second_words) = ranked
        if first_words - second_words >= config.TEACHER_AMBIGUITY_MARGIN * first_words:
            return TeacherGuess(first, ambiguous=False)
        hosts_in_top_two = self._hosts() & {first, second}
        if len(hosts_in_top_two) == 1:
            return TeacherGuess(hosts_in_top_two.pop(), ambiguous=False)
        return TeacherGuess(first, ambiguous=True)

    def quality(self, duration_s: float | None) -> TranscriptQuality:
        """Text-side quality signals (HLD §9.2). duration_s is None when there is no recording."""
        if not self.speech:
            return TranscriptQuality(0.0 if duration_s else None, 0.0, 0.0, QualityLevel.POOR)
        coverage = self._coverage(duration_s)
        words_per_min = self._words_per_minute(duration_s)
        non_latin = self._non_latin_share()
        level = self._quality_level(coverage, words_per_min, non_latin)
        return TranscriptQuality(coverage, words_per_min, non_latin, level)

    def _words_by_speaker(self) -> dict[str, int]:
        words = {}
        for cue in self.speech:
            if cue.speaker != UNKNOWN_SPEAKER:
                words[cue.speaker] = words.get(cue.speaker, 0) + cue.words
        return words

    def _hosts(self) -> set[str]:
        """Speakers who shared computer audio; in Zoom only the host can."""
        return {cue.speaker for cue in self.transcript.cues if cue.media}

    def _speech_span(self) -> tuple[float, float]:
        return self.speech[0].start, max(cue.end for cue in self.speech)

    def _coverage(self, duration_s: float | None) -> float | None:
        if not duration_s:
            return None
        first, last = self._speech_span()
        return min((last - first) / duration_s, 1.0)

    def _words_per_minute(self, duration_s: float | None) -> float:
        first, last = self._speech_span()
        minutes = (duration_s or (last - first)) / 60
        if minutes <= 0:
            return 0.0
        return sum(cue.words for cue in self.speech) / minutes

    def _non_latin_share(self) -> float:
        letters = [ch for cue in self.speech for ch in cue.text if ch.isalpha()]
        if not letters:
            return 0.0
        return sum(not ch.isascii() for ch in letters) / len(letters)

    @staticmethod
    def _quality_level(coverage: float | None, words_per_min: float, non_latin: float) -> QualityLevel:
        if coverage is not None and coverage < config.QUALITY_POOR_COVERAGE:
            return QualityLevel.POOR
        if words_per_min < config.QUALITY_POOR_WPM or non_latin > config.QUALITY_MAX_NON_LATIN:
            return QualityLevel.POOR
        if coverage is not None and coverage < config.QUALITY_GOOD_COVERAGE:
            return QualityLevel.PARTIAL
        if words_per_min < config.QUALITY_GOOD_WPM:
            return QualityLevel.PARTIAL
        return QualityLevel.GOOD


def _to_seconds(stamp: str) -> float:
    """"01:02:03.250" or "02:03,250" → seconds."""
    parts = stamp.replace(",", ".").split(":")
    seconds = 0.0
    for power, part in enumerate(reversed(parts)):  # seconds, then minutes, then hours
        seconds += float(part) * 60**power
    return seconds
