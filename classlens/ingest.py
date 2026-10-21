"""Input handling: save uploads to a temp dir, read media metadata, pick the input mode."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from classlens import config

# Input modes (HLD §9.1). The mode decides which checks can run and caps confidence.
MODES = {
    "A": "Full analysis (recording + transcript)",
    "B": "Recording only: transcript will be generated on the server",
    "C": "Transcript only: camera and video checks are not possible",
    "D": "Audio only: transcript will be generated on the server",
    "E": "Video without audio or transcript: visual checks only, grade is provisional",
}


class IngestError(Exception):
    """Problem with the user's input. The message is shown to the user as-is."""


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    has_video: bool
    has_audio: bool
    width: int | None = None
    height: int | None = None


def save_upload(upload: BinaryIO, original_name: str, workdir: Path) -> Path:
    """Stream an upload to disk under a generic name (original filenames can contain names)."""
    path = workdir / f"input{Path(original_name).suffix.lower()}"
    with path.open("wb") as out:
        shutil.copyfileobj(upload, out, length=8 * 1024 * 1024)
    return path


def probe(path: Path) -> MediaInfo:
    """Read duration and stream types with ffprobe. Streams are matched by type, never by index."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=config.FFPROBE_TIMEOUT_S
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        raise IngestError(
            "This file could not be read as audio or video. It may be corrupt or incomplete."
        ) from err

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    # Cover art in audio files shows up as a video stream; it is not real video.
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    durations = [data.get("format", {}).get("duration")] + [s.get("duration") for s in streams]
    duration_s = max((float(d) for d in durations if d not in (None, "N/A")), default=0.0)
    if duration_s <= 0:
        raise IngestError("Could not determine the length of this recording.")
    if video is None and not has_audio:
        raise IngestError("This file has no video or audio stream.")

    return MediaInfo(
        duration_s=duration_s,
        has_video=video is not None,
        has_audio=has_audio,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
    )


def input_mode(media: MediaInfo | None, has_transcript: bool) -> str:
    """Pick the input mode from what was provided (HLD §9.1)."""
    if media is None:
        if has_transcript:
            return "C"
        raise IngestError("Upload a recording, a transcript, or both.")
    if media.has_video:
        if has_transcript:
            return "A"
        return "B" if media.has_audio else "E"
    return "C" if has_transcript else "D"
