"""Central settings. Tunable numbers live here, not in the logic."""

import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Environment variables (local: .env; deployed: the platform's secrets settings)
ACCESS_CODE_ENV = "APP_ACCESS_CODE"
API_KEY_ENV = "ANTHROPIC_API_KEY"

# Temporary evaluation key (HLD §8): a file holding "ANTHROPIC_API_KEY=…", read only when no key is
# configured, so a fresh clone runs without setup. Spend-limited and revoked after the evaluation.
# "" turns it off.
EVAL_KEY_URL = "https://drive.google.com/file/d/1GJ3hXKoOeKTioiXBG_yG_raYGAeGgTHq/view?usp=sharing"
EVAL_KEY_TIMEOUT_S = 10
# The file id in a Google Drive share link: ".../file/d/<id>/view?usp=sharing" or "...open?id=<id>"
DRIVE_FILE_ID = re.compile(r"/d/([\w-]{20,})|[?&]id=([\w-]{20,})")


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines → dict. Comments, blank lines and lines without "=" are skipped."""
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if sep and key and not key.startswith("#"):
            values[key] = value.strip().strip("\"'")
    return values


def load_env_file(path: Path = ENV_FILE) -> None:
    """Load the git-ignored .env, then the evaluation key if no Claude key is set by then. Real
    environment variables (and Streamlit secrets) always take precedence."""
    if path.exists():
        for key, value in parse_env(path.read_text(encoding="utf-8")).items():
            os.environ.setdefault(key, value)
    if not os.environ.get(API_KEY_ENV):
        load_eval_key()


def load_eval_key() -> None:
    """Fetch the evaluation key into memory only (never to disk or logs). Only ANTHROPIC_API_KEY is
    taken from the file, and only if it looks like a Claude key; any failure leaves no key set."""
    if not EVAL_KEY_URL:
        return
    try:
        with urllib.request.urlopen(direct_download_url(EVAL_KEY_URL), timeout=EVAL_KEY_TIMEOUT_S) as response:
            text = response.read(4096).decode("utf-8", errors="replace")
    except OSError:  # no network, timeout, link removed
        return
    key = parse_env(text).get(API_KEY_ENV, "")
    if key.startswith("sk-ant-"):
        os.environ[API_KEY_ENV] = key


def direct_download_url(url: str) -> str:
    """A Google Drive share link → its direct download link; any other link unchanged."""
    match = DRIVE_FILE_ID.search(url)
    if "drive.google.com" not in url or match is None:
        return url
    return f"https://drive.google.com/uc?export=download&id={match.group(1) or match.group(2)}"

# Accepted input: the class video only; the transcript is generated from its audio
VIDEO_EXTENSIONS = ["mp4", "mov", "mkv", "webm"]
FFPROBE_TIMEOUT_S = 60

# Speech-to-text (HLD §9.1): local faster-whisper on CPU
WHISPER_MODEL = "base"
WHISPER_THREADS = 2  # the free host has about 2 cores
WHISPER_BEAM_SIZE = 1  # greedy: 2x faster than the default 5 for 2 points less word recall (44-min class)
WHISPER_WINDOW_S = 600  # transcribe in 10-min pieces: a whole class at once peaked at 2.2 GB

# Video checks (HLD §6.2, §9.3): frames at teacher-speech moments, checked in memory with OpenCV.
# Thresholds measured on the 12 sample classes (Zoom speaker view, 1080p); see ai-logs/DECISIONS.md.
FACE_MODEL_PATH = ROOT / "assets" / "face_detection_yunet_2023mar.onnx"  # YuNet, MIT; OpenCV 5 has no Haar cascades
FACE_MIN_SCORE = 0.6  # detector confidence
VIDEO_SAMPLES = 120  # moments checked per class: about 70 s on 2 cores (Zoom keyframes are up to 30 s apart)
VIDEO_MIN_LINE_S = 2  # teacher lines shorter than this are skipped (Zoom switches the speaker view late)
VIDEO_MIN_TEACHER_MOMENTS = 20  # fewer teacher lines than this → evenly spaced moments instead
FRAME_WIDTH = 640  # frames are shrunk to this width before the checks
FREEZE_GAP_S = 1  # each moment is a pair of frames this far apart
SPEAKER_FACE_MIN_WIDTH = 0.08  # face at least this share of the frame width = speaker view (thumbnails: ~0.03)
GALLERY_MIN_FACES = 3  # this many faces = gallery view, the teacher can't be singled out
DARK_LUMA = 40  # brightness 0–255 below this is dark (Zoom's camera-off card is grey ~26)
CARD_MIN_DARK_SHARE = 0.9  # camera-off card: this share of the frame dark (the name is small white text)…
CARD_MAX_SATURATION = 10  # … and colourless
SCREEN_MIN_SHARPNESS = 600  # Laplacian variance: shared screens 650–3800, camera pictures 100–550
# Speaker thumbnail during screen share as (left, top, right, bottom) shares of the frame; faces seen at x 0.83–1, y 0–0.22
THUMBNAIL_BOX = (0.82, 0.0, 1.0, 0.24)
LOW_LIGHT_FACE_LUMA = 45  # mean face brightness 0–255 below this = poorly lit (sample faces: 20–127)
BLUR_MAX_SHARPNESS = 40  # Laplacian variance of a speaker-view picture below this = blurred
FREEZE_MAX_MOTION = 0.3  # mean pixel change 0–255 over FREEZE_GAP_S below this = frozen (moving faces: 0.8+)
EXAMPLE_MOMENTS = 3  # moments quoted per finding in the report

# Video → C6 / C7 scores and gates (HLD §6.1, §6.3)
CAMERA_OFF_MINOR = 0.05  # camera off in more than this share of teaching moments: one point off C6
CAMERA_OFF_GATE = 0.3  # … more than this: another point off, and a gate flag (an excellent sample class
                        # had it off 19% of the time, all in its first 15 min, without reviewer comment)
FACE_VISIBLE_MINOR = 0.7  # face found in less than this share of camera-on moments: one point off C6
FACE_VISIBLE_GATE = 0.3  # … less than this: another point off, and a gate flag
LOW_LIGHT_MAX = 0.3  # face poorly lit in more than this share: one point off C6
GALLERY_MAX = 0.5  # gallery view in more than this share: face checks skipped
FROZEN_MAX = 0.1  # frozen in more than this share of camera moments: one point off C7
BLURRY_MAX = 0.3  # blurred in more than this share of camera moments: one point off C7
GATE_CAPS = {1: "Average", 2: "Poor"}  # number of gate flags → best grade allowed (2 or more → Poor)

# Rubric (HLD §6.1): id → (name, weight)
CRITERIA = {
    "C1": ("Opening and rapport", 20),
    "C2": ("Individual engagement", 25),
    "C3": ("Tone and energy", 15),
    "C4": ("Lesson flow and closure", 15),
    "C5": ("Homework", 10),
    "C6": ("Teacher presence and setup", 10),
    "C7": ("Technical delivery", 5),
}

# Grade (HLD §6.3): weighted rubric score 0–100 → one of four labels. Initial bands, to be
# calibrated on the labelled set (scripts/evaluate.py).
GRADE_BANDS = [(78, "Excellent"), (62, "Good"), (48, "Average"), (0, "Poor")]  # (minimum score, grade)
PROVISIONAL_MIN_WEIGHT = 0.6  # assessed criteria must carry this share of the total weight

# Claude calls (HLD §7)
MODEL = "claude-opus-5-5"
EFFORT = "medium"  # rubric judgement
MAX_TOKENS = 16000
AI_MAX_ATTEMPTS = 2  # one retry when the answer is truncated or doesn't match the schema
FALLBACK_BETA = "server-side-fallback-2026-07-01"
PROMPT_VERSION = "judge_v3"
ROLES_PROMPT_VERSION = "roles_v1"
ROLES_EFFORT = "low"  # labelling lines teacher / student / media is a simple task
PROMPTS_DIR = ROOT / "prompts"
MAX_BLOCK_S = 60  # longest merged transcript line shown to the model
EVIDENCE_TOLERANCE_S = 5
EVIDENCE_MIN_MATCH = 0.8  # share of a quote's characters found, in order, in the cited line
RUN_LOG_PATH = ROOT / "logs" / "runs.jsonl"  # git-ignored: one JSON line per analysis and per AI call
PRICE_PER_MTOK = {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20}  # Opus 5.5, USD

# Transcript structure (HLD §6.2, §9.2)
OPENING_WINDOW_MIN = 10
CLOSING_WINDOW_MIN = 10
TEACHER_AMBIGUITY_MARGIN = 0.10  # top two speakers closer than this share of words → ask the user
LONG_GAP_S = 20

# Transcript quality levels (HLD §9.2)
QUALITY_GOOD_COVERAGE = 0.8
QUALITY_POOR_COVERAGE = 0.5
QUALITY_GOOD_WPM = 60
QUALITY_POOR_WPM = 25
QUALITY_MAX_NON_LATIN = 0.3
