"""Ingest tests on synthetic media generated with ffmpeg (no real recordings)."""

import io
import shutil
import subprocess

import pytest

from classlens.ingest import IngestError, probe, run_id, save_upload

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
    assert info.has_audio
    assert (info.width, info.height) == (320, 240)
    assert info.duration_s == pytest.approx(2, abs=0.2)


@needs_ffmpeg
def test_probe_video_without_audio(tmp_path):
    info = probe(make_media(tmp_path / "a.mp4", audio=False))
    assert not info.has_audio


@needs_ffmpeg
def test_probe_rejects_audio_only(tmp_path):
    with pytest.raises(IngestError):
        probe(make_media(tmp_path / "a.m4a", video=False))


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


def test_run_id_depends_on_content_not_name(tmp_path):
    first, second, other = tmp_path / "B123 Teacher.mp4", tmp_path / "input.mp4", tmp_path / "x.mp4"
    for path, data in [(first, b"same video"), (second, b"same video"), (other, b"another video")]:
        path.write_bytes(data)
    assert run_id(first) == run_id(second) != run_id(other)
    assert len(run_id(first)) == 12
