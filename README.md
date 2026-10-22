# ClassLens

Assesses the quality of a recorded online class and grades it **Poor / Average / Good / Excellent**, with specific, timestamped observations.

Design: [docs/HLD.md](docs/HLD.md) · AI interaction history: [ai-logs/](ai-logs/)

## How it works

Upload a class video (mp4, mov, mkv or webm, up to 500 MB). On the server: speech-to-text with a local Whisper model → names replaced with codes (T, S, N1…) → Claude labels each line teacher / student / shared media → interaction metrics → Claude scores a 7-criterion rubric with timestamped evidence → code turns the scores into a 0–100 score and a grade. Video and audio never leave the server; only the de-identified transcript goes to the Claude API.

A 44-minute class takes about 2.5 minutes on a laptop (Whisper about 2 min, Claude about 35 s) and about $0.15 in API calls. One analysis runs at a time; others wait their turn.

## Run locally (no credentials needed)

Requires Python 3.11, `ffmpeg` (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Ubuntu) and an internet connection.

```bash
git clone https://github.com/Ashish94312/classlens.git
cd classlens
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/streamlit run app.py
```

Open the address it prints (usually http://localhost:8501), upload a class video and press **Analyse**. No API key, access code or `.env` file is needed:

- **Claude key:** during the evaluation the app loads a temporary key automatically from a link in `classlens/config.py` (`EVAL_KEY_URL`). It is a separate key with a spending limit, kept in memory only (never written to disk or logs), and will be revoked after the evaluation.
- **Access code:** only the hosted app asks for one; a local run opens directly.

The first analysis also downloads the Whisper speech-to-text model (about 150 MB), once.

**Using your own Claude key instead** (for example after the evaluation key is revoked): put it in a `.env` file (`cp .env.example .env`, then fill in `ANTHROPIC_API_KEY`) or export it in the terminal. A key you configure always takes precedence over the evaluation key.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Optional: your own Claude key. Without any key the app stops after speech-to-text and says why |
| `APP_ACCESS_CODE` | Optional: require an access code (the hosted app sets one; unset = no gate) |

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
