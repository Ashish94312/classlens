"""TranscriptParser and TranscriptAnalyzer on synthetic transcripts (fictional names only)."""

import pytest

from classlens.models import UNKNOWN_SPEAKER, Cue, QualityLevel, Transcript
from classlens.transcript import TranscriptAnalyzer, TranscriptParser

ZOOM_VTT = """WEBVTT

1
00:00:05.000 --> 00:00:07.500
Tara Quill: Hello everyone, can you hear me?

2
00:00:08.000 --> 00:00:09.000
Arjun: Yes ma'am!

3
00:01:10.000 --> 00:01:20.000
Audio shared by Tara Quill: Welcome to today's video about forks.

4
01:02:03.250 --> 01:02:05.000
Tara Quill: Okay, that's all for today,
see you next class. Bye!
"""


def parse(raw: str) -> list[Cue]:
    return TranscriptParser().parse(raw).cues


def analyzer(cues: list[Cue]) -> TranscriptAnalyzer:
    return TranscriptAnalyzer(Transcript(cues))


def cue(speaker, words, start=0.0, media=False, text=None):
    return Cue(start, start + 1, speaker, text or " ".join(["word"] * words), media)


# --- TranscriptParser ---

def test_parse_zoom_vtt():
    cues = parse(ZOOM_VTT)
    assert [c.speaker for c in cues] == ["Tara Quill", "Arjun", "Tara Quill", "Tara Quill"]
    assert cues[0].start == 5.0 and cues[0].end == 7.5
    assert cues[2].media and not cues[0].media
    assert cues[3].start == pytest.approx(3723.25)
    assert cues[3].text == "Okay, that's all for today, see you next class. Bye!"


def test_parse_srt_with_bom_and_comma_millis():
    srt = "﻿1\r\n00:00:01,000 --> 00:00:02,500\r\nArjun: Hi!\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nRohan: Hello\r\n"
    assert [(c.speaker, c.start, c.end) for c in parse(srt)] == [("Arjun", 1.0, 2.5), ("Rohan", 3.0, 4.0)]


def test_parse_voice_tags_settings_and_missing_speakers():
    vtt = (
        "WEBVTT\n\nNOTE generated\n\n"
        "00:00:01.000 --> 00:00:02.000 align:start position:0%\n<v Kavya>Which piece?</v>\n\n"
        "00:00:03.000 --> 00:00:04.000\nno speaker label here\n\n"
        "00:00:05.000 --> 00:00:06.000\n\n"
    )
    assert [(c.speaker, c.text) for c in parse(vtt)] == [
        ("Kavya", "Which piece?"),
        (UNKNOWN_SPEAKER, "no speaker label here"),
    ]


def test_parse_does_not_treat_clock_times_as_speakers():
    assert parse("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n10:30 is when class starts\n")[0].speaker == UNKNOWN_SPEAKER


def test_parse_sorts_cues_by_start():
    vtt = "WEBVTT\n\n00:00:09.000 --> 00:00:10.000\nB: later\n\n00:00:01.000 --> 00:00:02.000\nA: first\n"
    assert [c.speaker for c in parse(vtt)] == ["A", "B"]


# --- TranscriptAnalyzer.teacher ---

def test_teacher_by_words():
    guess = analyzer([cue("Tara", 100), cue("Arjun", 20), cue("Rohan", 30)]).teacher()
    assert guess.speaker == "Tara" and not guess.ambiguous


def test_teacher_host_wins_near_tie():
    guess = analyzer([cue("Arjun", 100), cue("Tara", 95), cue("Tara", 50, media=True)]).teacher()
    assert guess.speaker == "Tara" and not guess.ambiguous


def test_teacher_flags_ambiguous_tie():
    assert analyzer([cue("Arjun", 100), cue("Tara", 95)]).teacher().ambiguous


def test_teacher_without_labels():
    guess = analyzer([cue(UNKNOWN_SPEAKER, 50)]).teacher()
    assert guess.speaker == UNKNOWN_SPEAKER and guess.ambiguous


# --- TranscriptAnalyzer.quality ---

def test_quality_levels():
    talk = [cue("Tara", 80, start=60.0 * m) for m in range(60)]
    assert analyzer(talk).quality(duration_s=3600).level == QualityLevel.GOOD
    assert analyzer(talk[:20]).quality(duration_s=3600).level == QualityLevel.POOR  # a third of the class
    sparse = [cue("Tara", 10, start=60.0 * m) for m in range(60)]
    assert analyzer(sparse).quality(duration_s=3600).level == QualityLevel.POOR
    assert analyzer(talk).quality(duration_s=None).coverage is None
    script = [cue("Tara", 0, start=60.0 * m, text="നമസ്കാരം " * 80) for m in range(60)]
    assert analyzer(script).quality(duration_s=3600).level == QualityLevel.POOR
