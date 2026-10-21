# Decision log

Assistant: Claude Code (Claude Opus 5.5). Entries are newest last.

## Session 01 — 2026-10-22 — Research and HLD

**Prompt (summary):** Build an AI app that grades online class recordings (Poor/Average/Good/Excellent) with specific feedback based on `feedbacks.pdf`; data must not be exposed; use the Claude API; pick a free, simple deployment (Streamlit-style prototype); track how AI is used; produce a plan, workflow and HLD before implementing. Follow-ups: keep a redacted log of AI conversations; keep code quality high and dependencies minimal.

**What the AI did**

- Read the challenge brief and reviewer feedback; probed all 12 recordings with `ffprobe`; inspected the Zoom VTT format; sampled 4 frames to understand the screen layout.
- Ran a quick exploratory script over the 10 labelled transcripts (talk share, turn switches, questions, praise, keyword counts).
- Wrote `docs/HLD.md`, `.gitignore`, and this folder.

**Decisions**

| Decision | Why | Alternatives rejected |
|---|---|---|
| Hybrid scoring: deterministic metrics + LLM rubric judge; final grade computed in code | Keyword signals proved misleading (connectivity words peak in an Excellent class), but metrics like turn-taking do track quality; code-computed grade is reproducible | LLM-only grade (unstable, hard to defend); rules-only (can't judge rapport/tone) |
| Rubric of 7 criteria taken from reviewer feedback themes | Grounds the model in what the reviewers actually reward | Training a classifier on 10 samples (would overfit) |
| No video frames or audio sent to any external AI | Children are identifiable on camera; brief requires confidentiality | Vision LLM on frames |
| Pseudonymise transcript (`T`, `S1..Sn`) before the LLM call | Minimise personal data sent externally | Sending raw transcript |
| Evidence validator (timestamp + fuzzy quote match) | Forces specific, checkable feedback; measures hallucination | Trusting LLM citations |
| Excluded bitrate, resolution, duration as quality signals | They vary with content type, not teaching | — |
| Hugging Face Spaces (Docker, free CPU) | 16 GB RAM handles large videos; ffmpeg via apt; secrets | Streamlit Community Cloud (tight memory), Render (512 MB) |
| Minimal deps: streamlit, anthropic, opencv-python-headless, numpy (+ optional faster-whisper) | User asked for simple code with few libraries | LangChain, librosa, moviepy, webvtt-py, pyannote |
| `claude-opus-5-5`, effort `medium`, structured output via `messages.parse` + Pydantic | Pydantic ships with the SDK; schema-validated output | Free-text parsing |

**Open questions for the user:** "Known quality issues" → Poor? Is the Anthropic API acceptable for pseudonymised transcript text? Public or private GitHub repo?

### Follow-up — data rules

**Prompt (summary):** The brief lets us choose any AI model/API; the requirement is to handle the data rules properly. How?

**Decision:** Use the Claude API, enforced by data minimisation (HLD §8). Each brief rule maps to code-level controls:

| Rule | Controls |
|---|---|
| R1 confidentiality | `.gitignore` + `.dockerignore`; pre-commit `check_clean.sh` blocks media/VTT/PDF and real names; synthetic test fixtures; aggregate-only eval results |
| R2 no public exposure | Access-code gate; temp-dir processing deleted after every run; frames piped to NumPy (never written); no storage or media shown back; metadata-only logs |
| R3 permitted processing, children identifiable | Face and voice never leave the server (local OpenCV, local Whisper); single LLM exit point `build_llm_payload()` with a name guard that refuses to send; local-only mode switch |

### Follow-up — video frames

**Prompt (summary):** Are video frames sent to the LLM? How is video quality assessed?

**Decision:** Frames are never sent to Claude. `video.py` analyses ~150 sampled frames locally with OpenCV and emits only aggregated facts (percentages, time ranges) that go into the prompt as text. Added frozen-video (frame-pair differencing) and blur (Laplacian variance) checks to C7 to cover technical video quality. Vision LLM rejected: student faces appear in speaker view.

### Follow-up — edge cases

**Prompt (summary):** Inputs won't always be clean: laggy video, wrong transcripts, video without transcript, transcript without video. How is that handled?

**Decision:** Added HLD §9. Five input modes (full, video only, transcript only, audio only, video without audio or transcript), chosen automatically and shown in the report. Missing evidence makes a criterion *not assessed* instead of scoring it low; weights renormalise over assessed criteria; below 60% coverage the grade is marked Provisional. Specific handling for garbled/partial/mismatched transcripts (quality score, audio–transcript alignment), clipped recordings (opening/closing "not captured"), frozen video (only counted while the teacher's face is on screen, so static screen share isn't a false freeze), and AI failures (fallback to local-only mode). Edge-case test variants defined in §9.6. Plan grows to ≈6 h with a cut order.

**Self-correction:** session 01 research printed speaker-name counts and viewed sample frames through the AI assistant. From session 02, real data goes only through local scripts that print aggregates; development uses synthetic fixtures.

## Session 02 — 2026-10-22 — Phase 0: skeleton and deploy check

**Prompt (summary):** Start implementing per the plan; the report should be shown inside the hosted app. Hosting: use whatever is suggested; keep everything private until told otherwise.

**What the AI did**

- Built the skeleton: `classlens/config.py`, `classlens/ingest.py` (upload to temp dir under a generic filename, `ffprobe` metadata with streams matched by type, input-mode selection A–E), `app.py` (access-code gate, data notice, uploaders, temp-dir cleanup, uploader reset after each run so files leave server memory), Dockerfile, `.dockerignore`, Streamlit config, pre-commit guard, README.
- Tests: 13 passing, using synthetic media generated with `ffmpeg` (no real recordings). Access gate checked with Streamlit `AppTest`.
- Verified the pre-commit guard blocks a staged PDF from the dataset.

**Decisions**

| Decision | Why |
|---|---|
| Host on a private Hugging Face Space (Docker); private GitHub repo | User asked to keep everything private for now; HF gives 16 GB RAM for large videos and Whisper, Streamlit Community Cloud is too tight |
| Upload to HF from a `git archive` export, not the working folder | Guarantees only tracked files leave the machine; the working folder also holds the recordings |
| Audio files with cover art: ignore `attached_pic` video streams | Otherwise an `.mp3` would be treated as video |
| `anthropic` SDK is 2.0.0 (newer than the reference docs) | Check its API before writing the LLM code in Phase 2 |
