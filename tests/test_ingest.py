"""Ingest tests on synthetic media generated with ffmpeg (no real recordings)."""

import io
import shutil
import subprocess

import pytest

from classlens.ingest import IngestError, MediaInfo, input_mode, probe, save_upload

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_media(path, *, video=True, audio=True, seconds=2):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if video:
        cmd += ["-f", "lavfi", "-i", f"testsrc=size=320x240:rate=10:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


@needs_ffmpeg
def test_probe_video_with_audio(tmp_path):
    info = probe(make_media(tmp_path / "a.mp4"))
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (320, 240)
    assert info.duration_s == pytest.approx(2, abs=0.2)


@needs_ffmpeg
def test_probe_video_without_audio(tmp_path):
    info = probe(make_media(tmp_path / "a.mp4", audio=False))
    assert info.has_video and not info.has_audio


@needs_ffmpeg
def test_probe_audio_only(tmp_path):
    info = probe(make_media(tmp_path / "a.m4a", video=False))
    assert info.has_audio and not info.has_video


@needs_ffmpeg
def test_probe_rejects_corrupt_file(tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video" * 100)
    with pytest.raises(IngestError):
        probe(path)


def test_save_upload_uses_generic_name(tmp_path):
    path = save_upload(io.BytesIO(b"data"), "B123 Teacher Name - 2026.MP4", tmp_path)
    assert path.name == "input.mp4"
    assert path.read_bytes() == b"data"


@pytest.mark.parametrize(
    ("media", "has_transcript", "expected"),
    [
        (MediaInfo(60, has_video=True, has_audio=True), True, "A"),
        (MediaInfo(60, has_video=True, has_audio=True), False, "B"),
        (None, True, "C"),
        (MediaInfo(60, has_video=False, has_audio=True), True, "C"),
        (MediaInfo(60, has_video=False, has_audio=True), False, "D"),
        (MediaInfo(60, has_video=True, has_audio=False), False, "E"),
        (MediaInfo(60, has_video=True, has_audio=False), True, "A"),
    ],
)
def test_input_mode(media, has_transcript, expected):
    assert input_mode(media, has_transcript) == expected


def test_input_mode_requires_some_input():
    with pytest.raises(IngestError):
        input_mode(None, has_transcript=False)
