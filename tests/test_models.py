from classlens.models import Cue, QualityLevel, Transcript


def test_transcript_helpers():
    transcript = Transcript([Cue(5, 9, "T", "two words"), Cue(10, 70, "T", "video", media=True)])
    assert transcript.start() == 5 and transcript.end() == 70
    assert [cue.text for cue in transcript.speech()] == ["two words"]
    assert transcript.cues[0].words == 2


def test_quality_level_reads_as_plain_text():
    assert f"{QualityLevel.PARTIAL}" == "partial"
