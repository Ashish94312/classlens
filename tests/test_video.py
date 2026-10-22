"""Video checks on synthetic frames and a generated video (no real recordings, no faces of real people)."""

import shutil
import subprocess

import cv2

import numpy as np
import pytest

from classlens import config
from classlens.models import Cue, Transcript
from classlens.video import (
    FaceFinder,
    FrameCheck,
    FrameChecker,
    Layout,
    VideoAnalyzer,
    VideoError,
    describe,
    sample_times,
    summarise,
)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

WIDTH, HEIGHT = 1280, 720  # shrunk to FRAME_WIDTH (640) for the main checks
BIG_FACE = (250, 100, 120, 150)  # in the shrunk frame: 120 / 640 = 19% of the width → speaker view
THUMB_FACE = (60, 30, 50, 60)  # inside the full-resolution thumbnail crop


class FakeFaces:
    """Returns the given boxes for the shrunk frame and for the thumbnail crop."""

    def __init__(self, frame=(), thumbnail=()):
        self.frame, self.thumbnail = list(frame), list(thumbnail)

    def find(self, image):
        return self.frame if image.shape[1] == config.FRAME_WIDTH else self.thumbnail


def plain(luma, colour=False):
    frame = np.full((HEIGHT, WIDTH, 3), luma, np.uint8)
    if colour:
        frame[..., 2] = min(255, luma * 2)  # a reddish picture: not the colourless camera-off card
    return frame


def chessboard(thumbnail_luma=None):
    """Sharp black-and-white squares like a shared board; optionally a flat top-right thumbnail."""
    squares = (np.indices((HEIGHT, WIDTH)) // 40).sum(axis=0) % 2 * 255
    frame = np.repeat(squares[..., None], 3, axis=2).astype(np.uint8)
    if thumbnail_luma is not None:
        left, top, right, bottom = config.THUMBNAIL_BOX
        frame[int(top * HEIGHT) : int(bottom * HEIGHT), int(left * WIDTH) :] = thumbnail_luma
    return frame


def check(first, faces=FakeFaces(), second=None):
    return FrameChecker(faces).check(10.0, first, first if second is None else second)


def test_speaker_view_with_face_measures_light_sharpness_and_motion():
    result = check(plain(30, colour=True), FakeFaces([BIG_FACE]), second=plain(80, colour=True))
    assert result.layout == Layout.SPEAKER and not result.camera_off
    assert result.face_luma < config.LOW_LIGHT_FACE_LUMA  # dark face
    assert result.sharpness == 0 and result.motion > config.FREEZE_MAX_MOTION


def test_identical_pair_has_no_motion():
    assert check(plain(120, colour=True), FakeFaces([BIG_FACE])).motion == 0


def test_dark_colourless_frame_is_the_camera_off_card():
    result = check(plain(26))
    assert result.layout == Layout.SPEAKER and result.camera_off and result.face_luma is None


def test_soft_lit_frame_without_face_is_camera_on_face_not_found():
    result = check(plain(120, colour=True))
    assert result.layout == Layout.SPEAKER and not result.camera_off and result.face_luma is None


def test_shared_screen_uses_the_thumbnail():
    with_face = check(chessboard(thumbnail_luma=150), FakeFaces(thumbnail=[THUMB_FACE]))
    assert with_face.layout == Layout.SCREEN and with_face.face_luma == 150
    lit_no_face = check(chessboard(thumbnail_luma=150))
    assert lit_no_face.layout == Layout.SCREEN and not lit_no_face.camera_off and lit_no_face.face_luma is None
    dark_no_face = check(chessboard(thumbnail_luma=10))
    assert dark_no_face.camera_off


def test_many_faces_is_gallery_view():
    faces = FakeFaces([BIG_FACE, (10, 10, 60, 60), (400, 10, 60, 60)])
    assert check(plain(120, colour=True), faces).layout == Layout.GALLERY


def test_summarise_counts_each_share_over_the_frames_that_can_show_it():
    checks = [
        FrameCheck(10, Layout.SPEAKER, False, 100, 300, 5.0),
        FrameCheck(20, Layout.SPEAKER, False, 30, 20, 0.1),  # dark, blurred, frozen
        FrameCheck(30, Layout.SPEAKER, True, None, None, None),  # camera off
        FrameCheck(40, Layout.SCREEN, False, 90, None, None),
        FrameCheck(50, Layout.SCREEN, False, None, None, None),  # face not visible
        FrameCheck(60, Layout.GALLERY, False, None, None, None),
    ]
    video = summarise(checks)
    assert video.frames == 6 and video.gallery == pytest.approx(1 / 6, abs=0.001)
    assert video.screen_share == pytest.approx(2 / 6, abs=0.001)
    assert video.camera_off == 0.2  # 1 of 5 outside gallery view
    assert video.face_visible == 0.75 and video.low_light == pytest.approx(1 / 3, abs=0.001)
    assert video.blurry == 0.5 and video.frozen == 0.5  # speaker-view frames with a face only
    assert (video.camera_off_at, video.no_face_at, video.frozen_at) == ([30], [50], [20])


def test_summarise_leaves_unmeasurable_shares_empty():
    video = summarise([FrameCheck(10, Layout.SPEAKER, True, None, None, None)])
    assert video.camera_off == 1.0 and video.face_visible is None and video.frozen is None
    assert describe(video) == [
        "1 moments checked while the teacher speaks: shared screen in 0%, gallery view in 0%",
        "Teacher's camera off in 100% of them (e.g. 00:10)",
    ]


def test_gallery_only_has_no_teacher_shares():
    video = summarise([FrameCheck(10, Layout.GALLERY, False, None, None, None)])
    assert video.gallery == 1.0 and video.camera_off is None and len(describe(video)) == 1


def test_describe_quotes_moments():
    video = summarise([FrameCheck(75, Layout.SPEAKER, False, 100, 300, 0.0), FrameCheck(130, Layout.SCREEN, False, None, None, None)])
    facts = describe(video)
    assert "Teacher's face visible in 50% of camera-on moments (not found e.g. 02:10)" in facts
    assert "Camera picture frozen in 100% and blurred in 0% of camera moments (frozen e.g. 01:15)" in facts


def test_sample_times_follow_long_teacher_lines():
    cues = [Cue(index * 10, index * 10 + 4, "T", "line") for index in range(30)]
    cues += [Cue(400, 401, "T", "short"), Cue(500, 510, "S", "student"), Cue(600, 610, "T", "video", media=True)]
    moments = sample_times(Transcript(cues), 3600)
    assert moments[:2] == [2, 12] and len(moments) == 30  # short, student and media lines skipped


def test_sample_times_spread_and_fallback():
    many = [Cue(index * 10, index * 10 + 4, "T", "line") for index in range(500)]
    moments = sample_times(Transcript(many), 6000)
    assert len(moments) == config.VIDEO_SAMPLES and moments[0] == 2 and moments[-1] > 4900
    even = sample_times(None, 1210)  # no transcript: evenly spaced
    assert len(even) == config.VIDEO_SAMPLES and even[0] == pytest.approx(1210 / (config.VIDEO_SAMPLES + 1))


def test_face_model_loads_and_finds_nothing_in_a_blank_frame():
    assert FaceFinder().find(np.zeros((360, 640, 3), np.uint8)) == []


@needs_ffmpeg
def test_analyser_reads_a_generated_video(tmp_path):
    path = tmp_path / "input.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=6",
                    str(path)], check=True)
    video = VideoAnalyzer(path, FakeFaces()).analyse([1, 2, 3, 30])  # 30 s is past the end: skipped
    assert video.frames == 3 and video.face_visible == 0


def test_unreadable_video_raises(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(VideoError):
        VideoAnalyzer(bad, FakeFaces()).analyse([1])


def test_missing_face_model_raises_video_error(tmp_path):
    with pytest.raises(VideoError):
        FaceFinder(tmp_path / "missing.onnx")


class BrokenFaces:
    def find(self, image):
        raise cv2.error("decoder failed")


@needs_ffmpeg
def test_opencv_failure_becomes_video_error(tmp_path):
    path = tmp_path / "input.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
                    str(path)], check=True)
    with pytest.raises(VideoError):
        VideoAnalyzer(path, BrokenFaces()).analyse([1])
