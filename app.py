"""ClassLens Streamlit UI. All processing happens on this server; see HLD §8."""

import hmac
import os
import tempfile
from pathlib import Path

import streamlit as st

from classlens import config
from classlens.ingest import MODES, IngestError, input_mode, probe, save_upload

DATA_NOTICE = (
    "Your recording is processed on this server and deleted when the analysis finishes. "
    "Video, audio and frames never leave the server. Only a de-identified transcript "
    "(names replaced with T, S1, S2…) is sent to the AI model."
)

st.set_page_config(page_title="ClassLens", page_icon="♟️", layout="centered")


def access_granted() -> bool:
    """Gate the app behind a shared access code. No code configured means local development."""
    expected = os.environ.get(config.ACCESS_CODE_ENV)
    if not expected or st.session_state.get("authorised"):
        return True
    code = st.text_input("Access code", type="password")
    if code and hmac.compare_digest(code, expected):
        st.session_state.authorised = True
        st.rerun()
    if code:
        st.error("Wrong access code.")
    return False


def analyse(recording, transcript) -> dict:
    """Run the pipeline inside a temp dir that is always removed afterwards."""
    with tempfile.TemporaryDirectory(prefix="classlens-") as workdir:
        media = probe(save_upload(recording, recording.name, Path(workdir))) if recording else None
        mode = input_mode(media, has_transcript=transcript is not None)
        return {"mode": mode, "media": media}


def show_result(result: dict) -> None:
    st.subheader("Result")
    st.write(f"**Input mode {result['mode']}:** {MODES[result['mode']]}")
    media = result["media"]
    if media:
        cols = st.columns(3)
        cols[0].metric("Duration", f"{media.duration_s / 60:.1f} min")
        cols[1].metric("Video", f"{media.width}×{media.height}" if media.has_video else "none")
        cols[2].metric("Audio", "yes" if media.has_audio else "none")
    st.caption("Assessment pipeline is under construction (HLD §16, phases 1–4).")


st.title("ClassLens")
st.caption("Assess the quality of a recorded online class.")

if not access_granted():
    st.stop()

st.info(DATA_NOTICE)

# Changing the key after each run drops the uploaded files from server memory.
round_id = st.session_state.setdefault("upload_round", 0)
recording = st.file_uploader("Class recording", type=config.MEDIA_EXTENSIONS, key=f"rec-{round_id}")
transcript = st.file_uploader(
    "Zoom transcript (optional, improves accuracy)",
    type=config.TRANSCRIPT_EXTENSIONS,
    key=f"vtt-{round_id}",
)

if st.button("Analyse", type="primary", disabled=not (recording or transcript)):
    try:
        with st.spinner("Analysing…"):
            st.session_state.result = analyse(recording, transcript)
    except IngestError as err:
        st.session_state.pop("result", None)
        st.error(str(err))
    else:
        st.session_state.upload_round += 1
        st.rerun()

if "result" in st.session_state:
    show_result(st.session_state.result)
