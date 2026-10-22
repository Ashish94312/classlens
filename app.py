"""ClassLens Streamlit UI (LLD §5.12). All processing happens on this server; see HLD §8.

Streamlit re-runs this script top to bottom on every interaction; state that must survive a
re-run lives in st.session_state ("authorised", "upload_round", "result").
"""

import hmac
import os
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from classlens import config
from classlens.asr import Transcriber
from classlens.ingest import IngestError, run_id, save_upload
from classlens.pipeline import Assessment, AssessmentPipeline
from classlens.runlog import RunLog, peak_memory_mb

DATA_NOTICE = (
    "Your recording is processed on this server and deleted when the analysis finishes. "
    "Video, audio and frames never leave the server. Only a de-identified transcript "
    "(names replaced with codes such as T, S, N1) is sent to the AI model."
)
BUSY_NOTICE = "Another assessment is running on this server. Yours starts as soon as it finishes."
GRADE_ORDER = [grade for _, grade in reversed(config.GRADE_BANDS)]  # Poor … Excellent


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


def upload_widget():
    """Recording uploader. Its key changes after each analysis (see run_analysis), which drops
    the uploaded file from server memory."""
    round_id = st.session_state.setdefault("upload_round", 0)
    return st.file_uploader("Class recording", type=config.VIDEO_EXTENSIONS, key=f"rec-{round_id}")


@st.cache_resource
def pipeline() -> AssessmentPipeline:
    """One Whisper model and one Claude client per server process, created on the first analysis."""
    return AssessmentPipeline(Transcriber())


def analyse(recording, facts: dict, on_step) -> dict:
    """Run the pipeline inside a temp dir that is always removed afterwards. Adds counts and
    timings to facts as it goes (for the run log, even if a step fails)."""
    with tempfile.TemporaryDirectory(prefix="classlens-") as workdir:
        path = save_upload(recording, recording.name, Path(workdir))
        facts["run_id"] = run_id(path)
        return {"assessment": pipeline().run(path, facts, on_step)}


@st.cache_resource
def analysis_lock() -> threading.Lock:
    """Shared by every session: one analysis at a time, because two Whisper runs at once could run
    the free host out of memory and restart the app for everyone."""
    return threading.Lock()


def run_analysis(recording) -> None:
    """Wait for any other analysis, analyse, keep the result for the next re-run, and reset the
    uploader. Every run, whatever its outcome, writes one "analysis" line to the run log."""
    lock, facts, outcome = analysis_lock(), {}, "error"
    started = time.perf_counter()
    if not lock.acquire(blocking=False):
        st.info(BUSY_NOTICE)
        lock.acquire()
    try:
        facts["waited_s"] = round(time.perf_counter() - started, 1)
        with st.status("Analysing… a full class takes several minutes.") as status:
            st.session_state.result = analyse(recording, facts, lambda text: status.update(label=text))
        outcome = "ok"
    except IngestError as err:
        outcome = "rejected"
        st.session_state.pop("result", None)
        st.error(str(err))
        return
    except Exception as err:
        facts["error"] = type(err).__name__  # the type only: messages can quote file content
        raise
    finally:
        lock.release()
        facts.update(total_s=round(time.perf_counter() - started, 1), peak_memory_mb=round(peak_memory_mb()))
        RunLog().record("analysis", outcome, facts)
    st.session_state.upload_round += 1
    st.rerun()


def show_result(result: dict) -> None:
    assessment: Assessment = result["assessment"]
    if assessment.grade is None:
        st.warning(assessment.note)
        show_measurements(assessment)
        return
    show_grade(assessment)
    show_criteria(assessment)
    show_points(assessment)
    show_measurements(assessment)
    show_trace(assessment)


def show_grade(assessment: Assessment) -> None:
    grade, judgement = assessment.grade, assessment.judge.judgement
    st.header(f"Grade: {grade.grade}")
    st.write(f"Rubric score **{grade.score:.0f}/100** · AI's overall view: **{judgement.holistic_grade}**")
    if grade.provisional:
        st.warning(f"Provisional: only {grade.assessed_weight:.0%} of the rubric could be assessed from this recording.")
    if abs(GRADE_ORDER.index(grade.grade) - GRADE_ORDER.index(judgement.holistic_grade)) >= 2:
        st.warning("The rubric score and the AI's overall view are two grades apart; treat this result with caution.")
    if judgement.transcript_quality != "good":
        st.info(f"The transcript quality is {judgement.transcript_quality}, so some judgements rest on limited text.")
    st.write(judgement.summary)


def show_criteria(assessment: Assessment) -> None:
    st.subheader("Rubric")
    for criterion in sorted(assessment.judge.judgement.criteria, key=lambda c: c.criterion_id):
        name = config.CRITERIA[criterion.criterion_id][0]
        score = f"{criterion.score}/4" if criterion.assessed and criterion.score else "not assessed"
        with st.expander(f"{criterion.criterion_id} {name}: {score}"):
            st.write(criterion.rationale)
            for evidence in criterion.evidence:
                sign = "+" if evidence.polarity == "positive" else "−"
                st.markdown(f"{sign} `[{evidence.timestamp}]` “{evidence.quote}”: {evidence.observation}")


def show_points(assessment: Assessment) -> None:
    judgement = assessment.judge.judgement
    strengths, improvements = st.columns(2)
    strengths.subheader("Strengths")
    for point in judgement.strengths:
        strengths.markdown(f"`[{point.timestamp}]` {point.text} ({point.criterion_id})")
    improvements.subheader("To improve")
    for point in judgement.improvements:
        improvements.markdown(f"`[{point.timestamp}]` {point.text} ({point.criterion_id})")


def show_measurements(assessment: Assessment) -> None:
    st.subheader("Measured")
    cols = st.columns(3)
    cols[0].metric("Duration", f"{assessment.media.duration_s / 60:.0f} min")
    if assessment.quality:
        cols[1].metric("Transcript quality", assessment.quality.level)
        cols[2].metric("Words per minute", f"{assessment.quality.words_per_min:.0f}")
    metrics = assessment.metrics
    if metrics:
        cols = st.columns(3)
        cols[0].metric("Teacher share of talk", f"{metrics.teacher_talk_share:.0%}")
        cols[1].metric("Teacher/student switches", f"{metrics.turn_switches_per_min:.1f}/min")
        cols[2].metric("Teacher questions", f"{metrics.teacher_questions_per_min:.1f}/min")
        st.caption(f"Shared video or audio: {metrics.media_minutes:.0f} min · silences over {config.LONG_GAP_S} s: "
                   f"{metrics.long_gaps}. Speaker roles come from the transcript text and can be wrong on some lines.")


def show_trace(assessment: Assessment) -> None:
    trace = assessment.judge.trace
    with st.expander("AI trace"):
        st.write(
            f"Prompt {trace['prompt_version']} · {trace['served_model']} · effort {trace['effort']} · "
            f"{trace['input_tokens']:,} tokens in / {trace['output_tokens']:,} out · ~${trace['cost_usd']:.2f} · "
            f"{trace['latency_s']:.0f} s · evidence kept {trace['evidence_accepted']} of "
            f"{trace['evidence_accepted'] + trace['evidence_rejected']} (quotes not found in the transcript are dropped)"
        )


def main() -> None:
    st.set_page_config(page_title="ClassLens", page_icon="♟️", layout="centered")
    config.load_env_file()
    st.title("ClassLens")
    st.caption("Assess the quality of a recorded online class.")
    if not access_granted():
        st.stop()

    st.info(DATA_NOTICE)
    recording = upload_widget()
    if st.button("Analyse", type="primary", disabled=recording is None):
        run_analysis(recording)
    if "result" in st.session_state:
        show_result(st.session_state.result)


main()
