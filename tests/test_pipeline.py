"""AssessmentPipeline end to end on a generated video, with a fake transcriber and a fake Claude."""

import shutil
import subprocess

import anthropic
import pytest

from classlens.llm.judge import ClaudeJudge
from classlens.llm.roles import RoleLabeller
from classlens.llm.schema import RoleLabels
from classlens.models import UNKNOWN_SPEAKER, Cue, Transcript
from classlens.pipeline import NO_AUDIO, NO_SPEECH, AssessmentPipeline
from classlens.runlog import RunLog
from tests.fakes import REQUEST, FakeClient, judgement, response

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SPEECH = [
    Cue(0, 4, UNKNOWN_SPEAKER, "Hello Kabir, how was your tournament?"),
    Cue(5, 8, UNKNOWN_SPEAKER, "I won two games ma'am!"),
    Cue(3500, 3530, UNKNOWN_SPEAKER, "For homework solve puzzles 1 to 5. Bye everyone!"),
]


class FakeTranscriber:
    def __init__(self, cues):
        self.cues = cues

    def transcribe(self, path):
        return Transcript(self.cues)


def video(tmp_path, audio=True):
    path = tmp_path / "input.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5:duration=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


def pipeline(tmp_path, cues, *outcomes):
    client, log = FakeClient(*outcomes), RunLog(tmp_path / "runs.jsonl")
    return AssessmentPipeline(FakeTranscriber(cues), RoleLabeller(client, log), ClaudeJudge(client, log)), client


@needs_ffmpeg
def test_full_run_gives_a_grade_and_fills_facts(tmp_path):
    run, client = pipeline(tmp_path, SPEECH, response(RoleLabels(student_lines=[2], media_lines=[])), response(judgement()))
    facts = {}
    assessment = run.run(video(tmp_path), facts)

    # Both assessed criteria score 4 in the fake judgement. The test pattern has no face in it: the video
    # adds C6 = 2 (score (20 + 10 + 10/3) / 40 = 83.3, Excellent band) and the face gate caps it at Average.
    assert assessment.grade.score == 83.3 and assessment.grade.grade == "Average"
    assert assessment.video.face_visible == 0 and len(assessment.grade.flags) == 1
    assert "moments checked while the teacher speaks" in client.calls[1]["messages"][0]["content"]  # facts reach the judge
    assert assessment.metrics.teacher_talk_share > 0.5 and assessment.judge is not None
    assert "Kabir" not in client.calls[0]["messages"][0]["content"]  # names replaced before any call
    assert {"video_min", "has_audio", "transcription_s", "lines", "words", "video_s", "frames", "grade", "score",
            "gate_flags"} <= facts.keys()


@needs_ffmpeg
def test_no_audio_and_no_speech_are_explained_not_graded(tmp_path):
    silent, _ = pipeline(tmp_path, SPEECH)
    assessment = silent.run(video(tmp_path, audio=False), {})
    assert assessment.note == NO_AUDIO and assessment.grade is None and assessment.video.frames > 0
    empty, _ = pipeline(tmp_path, [])
    assessment = empty.run(video(tmp_path), {})
    assert assessment.note == NO_SPEECH and assessment.video is not None


@needs_ffmpeg
def test_ai_failure_keeps_text_quality_and_says_why(tmp_path):
    run, _ = pipeline(tmp_path, SPEECH, anthropic.APIConnectionError(request=REQUEST))
    facts = {}
    assessment = run.run(video(tmp_path), facts)
    assert assessment.grade is None and "Could not reach" in assessment.note
    assert assessment.quality is not None and facts["ai_skipped"] == "AIUnavailable"
    assert assessment.video is not None  # the video checks still run without the AI
