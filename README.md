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

## Deploy (Streamlit Community Cloud)

1. At [share.streamlit.io](https://share.streamlit.io), create an app from this repo, branch `main`, main file `app.py`.
2. Advanced settings: Python 3.11; Secrets:
   ```toml
   APP_ACCESS_CODE = "choose-a-code"
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
3. `packages.txt` installs `ffmpeg`; `requirements.txt` installs the Python packages.

A `Dockerfile` is included for running the same app on any container host.

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
