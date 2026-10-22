"""Input handling: save the uploaded video to a temp dir and read its metadata (LLD §5.3)."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from classlens import config
from classlens.models import MediaInfo

COPY_CHUNK_BYTES = 8 * 1024 * 1024
RUN_ID_BYTES = 1024 * 1024  # how much of the file the run id is computed from


class IngestError(Exception):
    """Problem with the user's input. The message is shown to the user as-is."""


def save_upload(upload, original_name: str, workdir: Path) -> Path:
    """Stream an upload (any file object opened in binary mode) to disk under a generic name
    (original filenames can contain names)."""
    path = workdir / f"input{Path(original_name).suffix.lower()}"
    with path.open("wb") as out:
        shutil.copyfileobj(upload, out, length=COPY_CHUNK_BYTES)
    return path


def run_id(path: Path) -> str:
    """Short SHA-256 of the file's first 1 MB: tells runs of the same video apart in the log
    without storing its name."""
    with path.open("rb") as file:
        return hashlib.sha256(file.read(RUN_ID_BYTES)).hexdigest()[:12]


def probe(path: Path) -> MediaInfo:
    """Read duration, video size and whether there is audio, with ffprobe."""
    data = _run_ffprobe(path)
    streams = data.get("streams", [])
    video = _real_video_stream(streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    duration_s = _duration(data)

    if duration_s <= 0:
        raise IngestError("Could not determine the length of this recording.")
    if video is None:
        raise IngestError("This file has no video. Upload the class recording (mp4, mov, mkv or webm).")
    return MediaInfo(
        duration_s=duration_s,
        has_audio=has_audio,
        width=video.get("width"),
        height=video.get("height"),
    )


def _run_ffprobe(path: Path) -> dict:
    command = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=config.FFPROBE_TIMEOUT_S
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        raise IngestError(
            "This file could not be read as audio or video. It may be corrupt or incomplete."
        ) from err
    return json.loads(result.stdout or "{}")


def _real_video_stream(streams: list[dict]) -> dict | None:
    """First video stream that is not cover art (audio files show cover art as a video stream)."""
    for stream in streams:
        is_cover_art = stream.get("disposition", {}).get("attached_pic")
        if stream.get("codec_type") == "video" and not is_cover_art:
            return stream
    return None


def _duration(data: dict) -> float:
    """Longest duration reported by the container or any stream (some files only report one)."""
    reported = [data.get("format", {}).get("duration")]
    reported += [stream.get("duration") for stream in data.get("streams", [])]
    valid = [float(value) for value in reported if value not in (None, "N/A")]
    return max(valid, default=0.0)
