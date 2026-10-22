"""Visual checks on the class video (HLD §5 step 6, §6.2, §9.3; LLD §5.20).

Frames are decoded into memory with OpenCV, checked and dropped: none is written to disk, shown or
sent anywhere. Only counts, shares and moments leave this module, as VideoFindings.

Zoom records the speaker view: the person speaking fills the frame (or Zoom's dark camera-off card
with their name), and while a screen is shared the speaker is a thumbnail in the top-right corner.
Frames are taken while the teacher speaks, so the speaker on view is the teacher.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

from classlens import config
from classlens.models import TEACHER_CODE, Transcript, VideoFindings
from classlens.timecode import format_time


class VideoError(Exception):
    """The video frames could not be read. The message is shown to the user as-is."""


class Layout(StrEnum):
    SPEAKER = "speaker"  # the teacher's camera (or camera-off card) fills the frame
    SCREEN = "screen"  # a shared screen; the teacher is the top-right thumbnail
    GALLERY = "gallery"  # several faces: gallery view


@dataclass(frozen=True)
class FrameCheck:
    """What one sampled moment shows."""

    at_s: float
    layout: Layout
    camera_off: bool
    face_luma: float | None  # mean brightness of the teacher's face; None when no face is found
    sharpness: float | None  # Laplacian variance of a speaker-view picture with a face
    motion: float | None  # mean pixel change over FREEZE_GAP_S, same frames as sharpness


def sample_times(transcript: Transcript | None, duration_s: float) -> list[float]:
    """Moments to check: the middle of teacher lines, spread over the class. Evenly spaced moments
    instead when there are too few teacher lines (no transcript, or no speech)."""
    moments = []
    if transcript is not None:
        for cue in transcript.speech():
            if cue.speaker == TEACHER_CODE and cue.end - cue.start >= config.VIDEO_MIN_LINE_S:
                moments.append((cue.start + cue.end) / 2)
    if len(moments) < config.VIDEO_MIN_TEACHER_MOMENTS:
        step = duration_s / (config.VIDEO_SAMPLES + 1)
        return [step * (number + 1) for number in range(config.VIDEO_SAMPLES)]
    if len(moments) <= config.VIDEO_SAMPLES:
        return moments
    step = len(moments) / config.VIDEO_SAMPLES
    return [moments[int(number * step)] for number in range(config.VIDEO_SAMPLES)]


class FrameReader:
    """Frames of one video, read into memory at chosen moments."""

    def __init__(self, media_path: Path):
        self._capture = cv2.VideoCapture(str(media_path))
        if not self._capture.isOpened():
            raise VideoError("The video frames could not be read, so the camera and screen checks were skipped.")
        frames_per_second = self._capture.get(cv2.CAP_PROP_FPS) or 25
        self._frames_per_gap = max(1, round(frames_per_second * config.FREEZE_GAP_S))

    def pair(self, at_s: float) -> tuple[np.ndarray, np.ndarray] | None:
        """The frame at at_s and the one FREEZE_GAP_S later (BGR), or None past the end. A seek
        decodes from the previous keyframe (Zoom: up to 30 s back), so the second frame is reached
        by decoding forward rather than seeking again: half the work."""
        self._capture.set(cv2.CAP_PROP_POS_MSEC, at_s * 1000)
        ok, first = self._capture.read()
        for _ in range(self._frames_per_gap - 1):
            ok = ok and self._capture.grab()
        if not ok:
            return None
        ok, second = self._capture.read()
        if not ok:
            return None
        return first, second

    def close(self) -> None:
        self._capture.release()


class FaceFinder:
    """YuNet face detector (OpenCV's FaceDetectorYN with the model file in assets/)."""

    def __init__(self, model_path: Path = config.FACE_MODEL_PATH):
        if not model_path.exists():  # assets/ not deployed: skip the checks rather than fail the analysis
            raise VideoError("The face-detection model is missing, so the camera and screen checks were skipped.")
        self._detector = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), config.FACE_MIN_SCORE)

    def find(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Face boxes (x, y, width, height) inside the image, widest first."""
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _, found = self._detector.detect(image)
        if found is None:
            return []
        boxes = []
        for row in found:
            x, y = max(0, int(row[0])), max(0, int(row[1]))
            boxes.append((x, y, int(row[2]), int(row[3])))
        return sorted(boxes, key=lambda box: box[2], reverse=True)


class FrameChecker:
    """Classifies one frame pair: layout, camera off, the teacher's face, light, sharpness, motion."""

    def __init__(self, faces: FaceFinder):
        self.faces = faces

    def check(self, at_s: float, first: np.ndarray, second: np.ndarray) -> FrameCheck:
        small = _shrink(first)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = self.faces.find(small)
        if len(faces) >= config.GALLERY_MIN_FACES:
            return FrameCheck(at_s, Layout.GALLERY, False, None, None, None)
        if faces and faces[0][2] >= config.SPEAKER_FACE_MIN_WIDTH * small.shape[1]:
            motion = _motion(gray, cv2.cvtColor(_shrink(second), cv2.COLOR_BGR2GRAY))
            return FrameCheck(at_s, Layout.SPEAKER, False, _mean_in(gray, faces[0]), _sharpness(gray), motion)
        if _is_camera_off_card(small, gray):
            return FrameCheck(at_s, Layout.SPEAKER, True, None, None, None)
        if _sharpness(gray) >= config.SCREEN_MIN_SHARPNESS:
            return self._check_thumbnail(at_s, first)
        return FrameCheck(at_s, Layout.SPEAKER, False, None, None, None)  # camera on, no face found

    def _check_thumbnail(self, at_s: float, frame: np.ndarray) -> FrameCheck:
        """Screen share: look for the teacher in the top-right thumbnail, at full resolution (the
        face there is about 60 px wide in a 1080p recording, too small once shrunk)."""
        thumbnail = _thumbnail(frame)
        gray = cv2.cvtColor(thumbnail, cv2.COLOR_BGR2GRAY)
        faces = self.faces.find(thumbnail)
        if faces:
            return FrameCheck(at_s, Layout.SCREEN, False, _mean_in(gray, faces[0]), None, None)
        camera_off = gray.mean() < config.DARK_LUMA  # no picture; a lit thumbnail without a face = face not visible
        return FrameCheck(at_s, Layout.SCREEN, camera_off, None, None, None)


class VideoAnalyzer:
    """Checks the frames at the given moments and sums up what they show."""

    def __init__(self, media_path: Path, faces: FaceFinder | None = None):
        self.media_path = media_path
        self.checker = FrameChecker(faces or FaceFinder())

    def analyse(self, moments: list[float]) -> VideoFindings:
        """Raises VideoError when no frame can be read or OpenCV fails on one."""
        try:
            checks = self.check_all(moments)
        except cv2.error as err:
            raise VideoError("The video frames could not be decoded, so the camera and screen checks were skipped.") from err
        if not checks:
            raise VideoError("No video frames could be read, so the camera and screen checks were skipped.")
        return summarise(checks)

    def check_all(self, moments: list[float]) -> list[FrameCheck]:
        """One FrameCheck per moment that can be read (moments past the end are skipped)."""
        reader = FrameReader(self.media_path)
        checks = []
        try:
            for at_s in moments:
                frames = reader.pair(at_s)
                if frames is not None:
                    checks.append(self.checker.check(at_s, *frames))
        finally:
            reader.close()
        return checks


def summarise(checks: list[FrameCheck]) -> VideoFindings:
    """Shares over the frames that can show each thing (e.g. face brightness only where a face is)."""
    in_view = [check for check in checks if check.layout != Layout.GALLERY]
    camera_on = [check for check in in_view if not check.camera_off]
    with_face = [check for check in camera_on if check.face_luma is not None]
    speaker_faces = [check for check in with_face if check.layout == Layout.SPEAKER]
    off = [check.at_s for check in in_view if check.camera_off]
    no_face = [check.at_s for check in camera_on if check.face_luma is None]
    frozen = [check.at_s for check in speaker_faces if check.motion < config.FREEZE_MAX_MOTION]
    dark = [check for check in with_face if check.face_luma < config.LOW_LIGHT_FACE_LUMA]
    blurry = [check for check in speaker_faces if check.sharpness < config.BLUR_MAX_SHARPNESS]
    examples = config.EXAMPLE_MOMENTS
    return VideoFindings(
        frames=len(checks),
        screen_share=_share(sum(1 for check in checks if check.layout == Layout.SCREEN), len(checks)),
        gallery=_share(len(checks) - len(in_view), len(checks)),
        camera_off=_share(len(off), len(in_view)),
        face_visible=_share(len(with_face), len(camera_on)),
        low_light=_share(len(dark), len(with_face)),
        blurry=_share(len(blurry), len(speaker_faces)),
        frozen=_share(len(frozen), len(speaker_faces)),
        camera_off_at=off[:examples],
        no_face_at=no_face[:examples],
        frozen_at=frozen[:examples],
    )


def describe(video: VideoFindings) -> list[str]:
    """The findings as sentences for the AI model and the report, e.g. "Teacher's camera off in 12%
    of the checked moments (e.g. 05:10, 12:31)"."""
    facts = [
        f"{video.frames} moments checked while the teacher speaks: shared screen in {video.screen_share:.0%}, "
        f"gallery view in {video.gallery:.0%}",
    ]
    if video.camera_off is not None:
        facts.append(f"Teacher's camera off in {video.camera_off:.0%} of them{_examples(video.camera_off_at)}")
    if video.face_visible is not None:
        facts.append(f"Teacher's face visible in {video.face_visible:.0%} of camera-on moments"
                     f"{_examples(video.no_face_at, 'not found')}")
    if video.low_light is not None:
        facts.append(f"Face poorly lit in {video.low_light:.0%} of moments with a face")
    if video.frozen is not None:
        facts.append(f"Camera picture frozen in {video.frozen:.0%} and blurred in {video.blurry:.0%} of "
                     f"camera moments{_examples(video.frozen_at, 'frozen')}")
    return facts


def _examples(moments: list[float], label: str = "") -> str:
    if not moments:
        return ""
    times = ", ".join(format_time(at_s) for at_s in moments)
    return f" ({label} e.g. {times})" if label else f" (e.g. {times})"


def _share(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(count / total, 3)


def _shrink(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= config.FRAME_WIDTH:
        return frame
    size = (config.FRAME_WIDTH, round(height * config.FRAME_WIDTH / width))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def _thumbnail(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    left, top, right, bottom = config.THUMBNAIL_BOX
    return frame[int(top * height) : int(bottom * height), int(left * width) : int(right * width)]


def _sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high for sharp edges (text, a chessboard), low for soft pictures."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _motion(gray: np.ndarray, later: np.ndarray) -> float:
    return float(np.abs(gray.astype(np.int16) - later.astype(np.int16)).mean())


def _mean_in(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x, y, width, height = box
    return float(gray[y : y + height, x : x + width].mean())


def _is_camera_off_card(image: np.ndarray, gray: np.ndarray) -> bool:
    """Zoom's camera-off card: almost all dark and colourless (the name is small white text)."""
    dark = (gray < config.DARK_LUMA).mean()
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 1].mean()
    return dark >= config.CARD_MIN_DARK_SHARE and saturation <= config.CARD_MAX_SATURATION
