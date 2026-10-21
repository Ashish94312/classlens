"""Central settings. Tunable numbers live here, not in the logic."""

# Environment variables (set as Space secrets in deployment)
ACCESS_CODE_ENV = "APP_ACCESS_CODE"

# Accepted inputs
MEDIA_EXTENSIONS = ["mp4", "mov", "mkv", "webm", "mp3", "m4a", "wav"]
TRANSCRIPT_EXTENSIONS = ["vtt", "srt"]
FFPROBE_TIMEOUT_S = 60
