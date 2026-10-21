---
title: ClassLens
emoji: ♟️
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# ClassLens

Assesses the quality of a recorded online class and grades it **Poor / Average / Good / Excellent**, with specific, timestamped observations.

Design: [docs/HLD.md](docs/HLD.md) · AI interaction history: [ai-logs/](ai-logs/)

## Run locally

Requires Python 3.11 and `ffmpeg`.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/streamlit run app.py
```

Optional environment variables:

| Variable | Purpose |
|---|---|
| `APP_ACCESS_CODE` | Access code required to use the app (unset = no gate, for local development) |
| `ANTHROPIC_API_KEY` | Claude API key (unset = local-only mode) |

## Tests

```bash
.venv/bin/python -m pytest
```

Tests use synthetic media and transcripts only.

## Data handling

Recordings are processed on the server and deleted after each run; video, audio and frames are never sent to any external service. See [HLD §8](docs/HLD.md#8-data-handling).

Before committing, install the guard that blocks media, transcripts and real names:

```bash
ln -sf ../../scripts/check_clean.sh .git/hooks/pre-commit
```
