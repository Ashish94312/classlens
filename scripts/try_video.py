"""Local-only: the video checks on the labelled recordings (HLD §6.2, §9.3; LLD §5.13). Teacher-speech
moments come from the Zoom VTT speaker labels (the app uses Whisper + Claude roles instead), so this
costs no Claude calls. Prints aggregates per batch id only; no frame is saved or shown.

Usage: .venv/bin/python -m scripts.try_video "<dataset dir>" [keys...]
"""

import sys
import time
from pathlib import Path

import numpy as np

from classlens.scoring import gate_flags, presence_score, technical_score
from classlens.video import Layout, VideoAnalyzer, sample_times, summarise
from scripts.dataset import iter_recordings, prepare


def percentiles(values: list[float]) -> str:
    """10th / 50th / 90th percentile, or "-" without values."""
    if not values:
        return "-"
    return "/".join(f"{value:.1f}" for value in np.percentile(values, [10, 50, 90]))


def main(dataset: Path, keys: set[str] | None) -> None:
    print("recording        frames  s/moment screen gallery cam-off face  dark  blur  frozen  C6 C7 flags")
    spread = []
    for recording in iter_recordings(dataset, keys):
        if recording.video_path is None:
            continue
        prepared = prepare(recording)
        started = time.perf_counter()
        checks = VideoAnalyzer(recording.video_path).check_all(sample_times(prepared.clean.transcript, prepared.duration_s))
        seconds = (time.perf_counter() - started) / max(1, len(checks))
        video = summarise(checks)
        shares = [video.screen_share, video.gallery, video.camera_off, video.face_visible, video.low_light,
                  video.blurry, video.frozen]
        cells = " ".join("    -" if share is None else f"{share:>5.0%}" for share in shares)
        print(f"{recording.name:<16} {video.frames:>6} {seconds:>8.2f}  {cells}  {presence_score(video)}  "
              f"{technical_score(video)} {len(gate_flags(video))}")
        faces = [check for check in checks if check.layout == Layout.SPEAKER and check.motion is not None]
        spread.append((recording.name, [check.sharpness for check in faces], [check.motion for check in faces]))
    print("\nspeaker-view frames with a face: sharpness and motion, 10th/50th/90th percentile (min motion)")
    for name, sharpness, motion in spread:
        lowest = f"{min(motion):.2f}" if motion else "-"
        print(f"{name:<16} sharpness {percentiles(sharpness):<20} motion {percentiles(motion):<16} ({lowest})")


if __name__ == "__main__":
    main(Path(sys.argv[1]), set(sys.argv[2:]) or None)
