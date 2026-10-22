# ClassLens

Assesses the quality of a recorded online class and grades it **Poor / Average / Good / Excellent**, with specific, timestamped observations.

Design: [docs/HLD.md](docs/HLD.md) · AI interaction history: [ai-logs/](ai-logs/)

## How it works

Upload a class video (mp4, mov, mkv or webm, up to 500 MB). On the server: speech-to-text with a local Whisper model → names replaced with codes (T, S, N1…) → Claude labels each line teacher / student / shared media → interaction metrics → Claude scores a 7-criterion rubric with timestamped evidence → code turns the scores into a 0–100 score and a grade. Video and audio never leave the server; only the de-identified transcript goes to the Claude API.

A 44-minute class takes about 2.5 minutes on a laptop (Whisper about 2 min, Claude about 35 s) and about $0.15 in API calls. One analysis runs at a time; others wait their turn.

## Run locally

Requires Python 3.11 and `ffmpeg`.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/streamlit run app.py
```

No setup is needed for the evaluation: when no Claude key is configured, the app loads a **temporary evaluation key** from a link in `classlens/config.py` (`EVAL_KEY_URL`). That key has a spending limit and will be revoked after the evaluation. It is kept in memory only, never written to disk or logs. To use your own key instead, set `ANTHROPIC_API_KEY` in the environment or in a `.env` file (`cp .env.example .env`); a configured key always wins.

The first analysis downloads the Whisper model (about 150 MB) once.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key; optional while the evaluation key is live. Without any key the app stops after speech-to-text and says why |
| `APP_ACCESS_CODE` | Access code required to use the app (unset = no gate, for local development) |

## Deploy (Streamlit Community Cloud)

1. Push the repository to GitHub (it can stay private).
2. At [share.streamlit.io](https://share.streamlit.io): **Create app** → *Deploy a public app from GitHub* → repository, branch `main`, main file `app.py`.
3. **Advanced settings**: Python 3.11; Secrets:
   ```toml
   APP_ACCESS_CODE = "choose-a-code"
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Deploy. `packages.txt` installs `ffmpeg`, `requirements.txt` the Python packages (first build takes a few minutes).
5. Run one sample class. **Manage app → Logs** shows one `"purpose": "analysis"` line per run with the real timings (`transcription_s`, `total_s`) and memory (`peak_memory_mb`).

Free apps sleep after a period without visitors; open the link shortly before it is tested. A `Dockerfile` is included to run the same app on any container host.

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
