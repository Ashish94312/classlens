"""Pseudonymiser and NameGuard on synthetic transcripts (fictional names only)."""

import pytest

from classlens.models import UNKNOWN_SPEAKER, Cue, Transcript
from classlens.privacy import NameGuard, PrivacyError, Pseudonymiser, display_name_tokens


def cue(speaker, text, media=False):
    return Cue(0, 1, speaker, text, media)


def run(cues, teacher="Tara Quill"):
    result = Pseudonymiser(teacher).apply(Transcript(cues))
    return result, [(c.speaker, c.text) for c in result.transcript.cues]


def test_display_name_tokens_ignore_devices_possessives_and_symbols():
    assert display_name_tokens("Zoya’s iPhone") == ["zoya"]
    assert display_name_tokens("♟️Kavya👑") == ["kavya"]
    assert display_name_tokens("__ISHAAN__MEHRA__") == ["ishaan", "mehra"]
    assert display_name_tokens("arjun.k@school") == ["arjun", "school"]
    assert display_name_tokens("user") == [] and display_name_tokens("HP") == []


def test_speakers_get_role_codes_in_order():
    _, out = run([cue("Tara Quill", "Hi"), cue("Arjun", "Hello"), cue("Rohan", "Hi"), cue("Arjun", "Yes")])
    assert [speaker for speaker, _ in out] == ["T", "S1", "S2", "S1"]


def test_names_replaced_inside_text():
    _, out = run([
        cue("Tara Quill", "Arjun, which piece can fork here? rohan's answer was close."),
        cue("Arjun", "Thank you Tara ma'am"),
        cue("Rohan", "Quill ma'am, Tara Quill is my teacher"),
    ])
    assert out[0][1] == "S1, which piece can fork here? S2's answer was close."
    assert out[1][1] == "Thank you T ma'am"
    assert out[2][1] == "T ma'am, T is my teacher"


def test_device_label_child_named_in_speech_gets_n_code():
    _, out = run([cue("Tara Quill", "Hello Ishaan! Ishaan, turn on your camera."), cue("Zoya’s iPhone", "ok")])
    assert out[0][1] == "Hello N1! N1, turn on your camera."
    assert out[1][0] == "S1"


def test_common_words_are_not_names():
    _, out = run([cue("Tara Quill", "Hi Everyone. Okay, good morning. Now, very good Knight move. Isn't it? Didn't you?")])
    assert out[0][1] == "Hi Everyone. Okay, good morning. Now, very good Knight move. Isn't it? Didn't you?"


def test_words_mostly_used_in_lowercase_are_not_names():
    _, out = run([
        cue("Tara Quill", "Similarly, the bishop moves. Bishop, then pawn. Hello Ishaan!"),
        cue("Arjun", "similarly I moved the pawn, and similarly the rook"),
    ])
    assert out[0][1] == "Similarly, the bishop moves. Bishop, then pawn. Hello N1!"


def test_name_sometimes_written_in_lowercase_is_still_a_name():
    """Speech-to-text may write a name in lowercase; one capital mid-sentence or as many capitals as
    lowercase uses is enough, and then every spelling is replaced."""
    clean, out = run([
        cue(UNKNOWN_SPEAKER, "Well done Kabir. Kabir, next one."),
        cue(UNKNOWN_SPEAKER, "kabir is right and kabir knows it"),
        cue(UNKNOWN_SPEAKER, "Ishaan. Ishaan, try. ishaan wins"),
    ], teacher=UNKNOWN_SPEAKER)
    assert [text for _, text in out] == ["Well done N1. N1, next one.", "N1 is right and N1 knows it", "N2. N2, try. N2 wins"]


def test_name_said_only_at_sentence_start_is_still_replaced():
    _, out = run([cue("Tara Quill", "Video, let us watch. Ishaan, your turn.")])
    assert out[0][1] == "Video, let us watch. N1, your turn."


def test_unlabelled_speech_to_text_names_mid_sentence_are_replaced():
    """Whisper output: no speaker labels, so only names said in the text can be found."""
    clean, out = run([
        cue(UNKNOWN_SPEAKER, "Now give the answer Rohan, and then ask Meera."),
        cue(UNKNOWN_SPEAKER, "We play the Sicilian on Monday. The knight moves first."),
    ], teacher=UNKNOWN_SPEAKER)
    assert out[0] == (UNKNOWN_SPEAKER, "Now give the answer N1, and then ask N2.")
    assert out[1][1] == "We play the Sicilian on Monday. The knight moves first."  # not names
    assert clean.name_tokens == {"rohan", "meera"}


def test_name_alone_at_line_start_is_replaced():
    clean, out = run([cue(UNKNOWN_SPEAKER, "Ravi."), cue(UNKNOWN_SPEAKER, "ok we wait for him")], teacher=UNKNOWN_SPEAKER)
    assert out[0][1] == "N1." and clean.name_tokens == {"ravi"}


def test_contact_details_removed():
    _, out = run([cue("Tara Quill", "Please mail me at tara.q@example.com or call +91 98765 43210")])
    assert out[0][1] == "Please mail me at [email] or call [phone]"


def test_media_cue_keeps_flag_and_unknown_stays_unknown():
    result, out = run([cue("Tara Quill", "Video time", media=True), cue(UNKNOWN_SPEAKER, "hello")])
    assert out == [("T", "Video time"), (UNKNOWN_SPEAKER, "hello")]
    assert result.transcript.cues[0].media


def test_no_teacher_identified_does_not_label_unknown_as_teacher():
    _, out = run([cue(UNKNOWN_SPEAKER, "hello"), cue("Arjun", "hi")], teacher=UNKNOWN_SPEAKER)
    assert [speaker for speaker, _ in out] == [UNKNOWN_SPEAKER, "S1"]


def test_guard_blocks_leftover_names_and_passes_clean_text():
    result, out = run([cue("Tara Quill", "Arjun, your move"), cue("Arjun", "ok")])
    guard = NameGuard(result.name_tokens)
    guard.check(" ".join(text for _, text in out))
    with pytest.raises(PrivacyError):
        guard.check("Report for ARJUN")


def test_guard_with_no_names_passes_everything():
    NameGuard(frozenset()).check("anything at all")


def test_known_names_are_replaced_even_in_lowercase():
    clean, out = run([cue(UNKNOWN_SPEAKER, "Well done Kabir, and tell meera too")], teacher=UNKNOWN_SPEAKER)
    assert out[0][1] == "Well done N1, and tell meera too"  # never capitalised: no rule finds it
    clean = Pseudonymiser(UNKNOWN_SPEAKER, frozenset({"meera"})).apply(Transcript([cue(UNKNOWN_SPEAKER, "Well done Kabir, and tell meera too")]))
    assert clean.transcript.cues[0].text == "Well done N1, and tell N2 too"
    assert clean.name_tokens == {"kabir", "meera"}

