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

### Follow-up — hosting changed to Streamlit Community Cloud

**Prompt (summary):** Can we use something other than Hugging Face, e.g. Streamlit hosting or Firebase? Keep everything private; it becomes public only when the user says. The GitHub repo will need to be public at submission so evaluators can run it.

**Finding:** Creating the Space failed: Hugging Face now requires a PRO subscription to host Docker/Gradio Spaces on free CPU, and the account is not PRO. Firebase was checked at the user's request: its free plan serves static files only; Python needs the Blaze plan with Cloud Run underneath, whose 32 MiB HTTP/1 request limit blocks direct uploads of 54–340 MB recordings.

**Decision:** Host on Streamlit Community Cloud (free, no card, private viewers while building). Added `packages.txt` (ffmpeg); re-enabled Streamlit's XSRF protection (it was only disabled for the HF iframe); removed the HF config block from the README. To fit ~2.7 GB RAM, Mode B will transcribe sampled windows (~25 min) instead of the full audio; the Drive-link input is the fallback if large uploads fail. The Dockerfile stays for portability. GitHub repo and app go public only on the user's instruction, after a pre-publish check of the full git history.

## Session 03 — 2026-10-22 — Phase 1: transcript layer

**Prompt (summary):** Test locally for now (Streamlit Cloud deploy later); move on to the next phase.

**What the AI did**

- `classlens/transcript.py`: tolerant WebVTT/SRT parser (BOM, cue settings, voice tags, missing speaker labels, `Audio shared by` cues flagged as media), teacher detection (most words; host wins a near tie; ambiguous ties flagged for the UI), text-side quality score, clip-boundary check.
- `classlens/privacy.py`: speakers → `T` / `S1..Sn`, names spoken in class → `N1..Nn`, contact details removed, outbound name guard.
- `classlens/metrics.py`: talk share, turn switches, questions, named questions, participation balance (Gini), praise, greetings, media minutes, long gaps.
- 37 unit tests on synthetic transcripts. Local-only scripts: `inspect_transcripts.py` (aggregates per recording) and `build_redact_list.py` (writes the git-ignored name list for the pre-commit guard; prints a count only).

**Findings on the 12 real transcripts (aggregates only)**

- Name guard passed on all 12; no real names in any project file.
- Quality: 7 "good", 5 "partial" (sparse transcripts at 30–48 words/min). The garbled Malayalam demo still reads as "partial" on text signals alone, which confirms the LLM's transcript-quality judgement is needed.
- Clip boundaries: all openings captured; one recording's closing not captured.
- "Students addressed by name" saturated at 100% once names spoken in class were counted, so it can't separate classes. Dropped from C2 scoring; turn switches, teacher talk share, questions/min and participation balance remain.

**Decisions**

| Decision | Why |
|---|---|
| A spoken word counts as a name only if it never appears in lowercase in the transcript | The first rule turned sentence-start words ("Similarly,", "Bishop,") into names; ASR capitalises real names consistently. False positives dropped sharply with no dictionary dependency |
| Over-replacing a few ordinary words is acceptable | Errs on the side of privacy; small readability cost for the LLM |
| Role/placeholder words ("demo", "teacher", "host"…) are never names | Found when the pre-commit scan flagged "demo" in the HLD |
| Dev scripts print counts only, never word lists | A first version printed dictionary words that included some first names; changed to counts |

## Session 04 — 2026-10-22 — Phase 2: Claude judge

**Prompt (summary):** Use the Claude API (asked about self-hosting a model instead; decided Claude only for now). Keep the API key in a `.env` file rather than shell exports. Asked what it costs.

**What the AI did**

- `.env` support without a new library (`config.load_env_file`); `.env.example` template; pre-commit guard now also blocks `.env`, `secrets.toml` and anything shaped like an Anthropic API key.
- `prompts/judge_v1.md`: rubric with 1–4 anchors per criterion written from the reviewer feedback, "not assessed" rules for clipped recordings, evidence rules, transcript-quality rules, prompt-injection rule.
- `classlens/judge.py`: payload builder (facts, metrics, phase-marked transcript; the single exit point with the name guard), Claude call via `beta.messages.parse` with a Pydantic schema, effort `medium`, server-side refusal fallback, cached system prompt, one retry on truncated or unreadable output, typed error handling → `JudgeUnavailable` (local-only fallback). Evidence validator drops quotes that can't be found at the cited time.
- `classlens/ailog.py`: one JSON line per call with tokens, cost, latency, prompt version, evidence accepted/rejected; no transcript text.
- 54 tests, all with a fake client. `scripts/try_judge.py` with `--dry-run` (no API calls).

**Findings**

- Payloads are 2.3k–9.6k tokens (+ ~2k system prompt): ≈ $0.08–0.17 per class, $1–2 for all 12.
- The name guard blocked one payload: "Video," only ever appeared at sentence start, so it was treated as a name and then matched the payload's own heading. Nothing was sent.

**Decisions**

| Decision | Why |
|---|---|
| Claude only; no self-hosted model for now | Free hosting can't run a useful open model; an 8B model locally is feasible but weaker on grounded judgement. Revisit as an optional local mode if time allows |
| Guard checks the recording-derived parts of the payload, not the fixed template | Template words ("video", "recording") are not personal data and caused a false block |
| Tried, then reverted: requiring a mid-sentence sighting before treating a sentence-start word as a name | Measured: it would have let ~62 non-dictionary words through, many likely children's names. Privacy first: over-replacement is accepted, common classroom words are listed instead |
| Pydantic schema lives in `judge.py` (no separate `models.py`) | Keeps the schema next to the only code that uses it |

## Session 05 — 2026-10-22 — Refactor to classes and detailed LLD

**Prompt (summary):** The user rated the code 4/10: too "algorithmic" (dense functions, clever idioms, few classes) and no LLD. They asked for a detailed LLD and HLD from which anyone can tell where each piece of code is, what every function and class does, and how everything connects.

**What the AI did**

- Wrote the LLD target structure first, then refactored the code to it: `models.py` (all shared data types, `InputMode` / `QualityLevel` enums), `timecode.py`, `TranscriptParser` + `TranscriptAnalyzer`, `Pseudonymiser` + `NameGuard`, `InteractionAnalyzer` (one method per metric), `llm/` package split into `schema.py`, `prompt.py` (`PromptBuilder`), `evidence.py` (`EvidenceValidator`), `judge.py` (`ClaudeJudge`, `CallStats`); `AICallLog`; `app.py` with `main()`; shared `scripts/dataset.py`.
- Proved the refactor changed no behaviour: SHA-256 fingerprints of nine outputs per recording (parsed cues, teacher, pseudonymised cues, name tokens, quality, boundaries, metrics, payload text and lines) for all 12 recordings, before and after: 0 differences.
- Tests reorganised one file per module: 54 → 77, all passing.
- Rewrote `docs/LLD.md` (v2): code map and "where is X?" index; module-dependency, data-flow and sequence diagrams; domain model field by field; per module every constant (with example matches), class, field and function (signature, steps, calls, callers) plus a call graph; system call graph; errors; tests map; planned interfaces; conventions; change log. An automatic check confirmed all 290 code symbols appear in the LLD.
- HLD component table and repository layout now name the real modules and classes and link to the LLD sections.

**Decisions**

| Decision | Why |
|---|---|
| Classes for multi-step processes, dataclasses/enums for data, small pure helpers as functions | Readable structure the LLD can describe one-to-one; avoids Java-style classes for one-liners |
| Explicit loops over clever comprehensions/idioms; every regex a named constant with an example | User found the dense style hard to follow |
| Behaviour fingerprint before any refactor | Makes "nothing changed" provable, not asserted |
| LLD completeness checked by script (code symbols vs document) | Keeps the "every function is documented" promise verifiable as the code grows |

## Session 06 — 2026-10-22 — Fewer imports

**Prompt (summary):** The user asked why the code uses `@dataclass(frozen=True)` and `typing` imports, and asked that every import be justified: if plain Python does the job simply, don't import.

**What the AI did**

- Audited every import. Removed five that built-ins replace in the same amount of code: `typing.BinaryIO` and `collections.abc.Iterator` (type hints only), `collections.Counter` (→ `dict` + `.get()`), `dataclasses.replace` (→ calling `Cue(...)`), `dataclasses.asdict` (→ `vars()`).
- Added LLD convention 10 ("every import earns its place") and updated the affected LLD rows. Tests: 77 passing.

**Decisions**

| Decision | Why |
|---|---|
| Keep `@dataclass(frozen=True)` | Hand-written classes would add ~15 lines each (≈10 classes); `frozen` stops one pipeline step changing data another step reads |
| Keep `enum`, `difflib`, `hmac`, `typing.Literal` | Plain version longer or riskier: fuzzy quote matching, constant-time secret compare, allowed values in Claude's answer schema |
| Stdlib import ≠ new dependency | Stdlib ships with Python; third-party packages still need the user's approval |

**Follow-up prompt (summary):** The user asked why keyword matching is used when the LLM can read context — e.g. a "hello" said mid-session is not the start of the class. Their view: send the whole transcript with names replaced and let the LLM judge; build an agent only if needed.

**What the AI did**

- Split the code into "must stay in code" (name removal before anything leaves the server, counting metrics, file parsing, teacher detection by word count) and "keyword guesses at meaning".
- Removed the guesses: `OPENING_MARKERS` / `CLOSING_MARKERS` and the "Opening/closing captured" hint sent to Claude, `GREETING` / `PRAISE` counts, and the unused `students_addressed_share`.
- Prompt v2: one sentence telling Claude that OPENING / MAIN / CLOSING are split by recording time, so it decides from the content whether the class really opens or closes in the clip.
- HLD (C1, C3, §6.2, §9.2 edge cases), LLD and tests updated. Tests: 77 → 75, all passing.

| Decision | Why |
|---|---|
| Claude, not keywords, decides greetings, praise and whether the clip includes the class opening/closing | Keyword rules misfire (late joiner's "hello", "great, now turn your camera on"); the hint could push Claude to score homework low instead of "not assessed"; HLD §2.3 already showed keyword counts mislead |
| Keep counting metrics, parsing, name removal and teacher detection in code | Exact, free, reproducible; LLMs miscount over long transcripts; names must be gone before the text leaves the server |
| One structured call, no agent | The whole pseudonymised transcript fits in one call and needs no tools; an agent adds cost, latency and run-to-run variation without new information |
| Prompt bumped to `judge_v2` (v1 kept) | Every logged result names the prompt version it came from |

**Follow-up prompt (summary):** The user pointed out that the brief only promises the class video: no transcript will be provided, so the transcript upload should go and the transcript should come from the video's audio.

**What the AI did**

- App takes one video upload (mp4, mov, mkv, webm). Removed the transcript uploader, audio-only uploads, `choose_mode`, `InputMode` and `MediaInfo.has_video`; `probe` rejects files without video; a video without audio shows a "visual checks only, provisional" notice.
- HLD: the old Mode B (local Whisper → pseudonymise → Claude labels teacher/student lines) is now the only path with audio; Mode E (silent video) stays; VTT-only edge cases and the VTT–video alignment check removed. LLD and tests updated: 75 → 66, all passing; app smoke-tested.
- `TranscriptParser` kept for offline scripts: the labelled set's Zoom VTTs are the only ground truth for checking Whisper's words and the role labeller.

| Decision | Why |
|---|---|
| Video is the only input | The brief says "accept a new recording"; a transcript is not promised |
| Keep the VTT parser offline only | Measures speech-to-text and role-labelling accuracy against real Zoom speaker labels |
| Teacher/student roles from one Claude call on pseudonymised lines; no diarization model | pyannote-style diarization is too heavy for the free host; individual students can't be told apart, so participation balance is dropped |

**Follow-up prompt (summary):** The user approved `faster-whisper`, and asked how large videos get onto the server (upload vs link, chunked upload).

**What the AI did**

- Added `faster-whisper==1.2.1` and `classlens/asr.py` › `Transcriber` (base model, int8, 2 CPU threads, VAD on; reads audio straight from the video). Unit test with a fake model; `scripts/try_asr.py` times Whisper on a labelled recording and prints word recall against the Zoom VTT (aggregates only).
- Checked Streamlit's source: uploaded files are held entirely in server memory (`MemoryUploadedFileManager`), so the 2048 MB upload limit is unsafe on a host with about 2.7 GB of RAM.

| Decision | Why |
|---|---|
| Local faster-whisper, not a cloud speech API | Children's audio must not leave the server; faster-whisper needs no PyTorch |
| Big files via link (server downloads to disk in chunks), uploads capped (proposed: 500 MB) | Streamlit keeps uploads in RAM; a resumable chunked browser upload would need a custom component, too much for the time left |

**Measurements (one 44-min labelled class, Mac, 2 CPU threads; aggregates only)**

| Setting | Time | × real time | Words (Zoom VTT 2,886) | Word recall vs VTT | Peak memory |
|---|---|---|---|---|---|
| Whole class in one call, beam 5 | 172 s | 15× | 2,880 | 0.82 | 2.2 GB |
| 10-min windows, beam 5 | 235 s | 11× | 2,903 | 0.82 | 1.6 GB |
| 10-min windows, beam 1 (chosen) | 118 s | 22× | 2,905 | 0.80 | 1.2 GB |

| Decision | Why |
|---|---|
| Transcribe in 10-min windows | Whisper builds input features for all audio it is given at once; the whole class peaked at 2.2 GB on a ~2.7 GB host |
| Greedy decoding (beam 1) | Twice as fast and lighter for 2 points of word recall; the rubric judges teaching behaviour, not exact words, and the Zoom VTT reference is itself machine transcription |

**Follow-up prompt (summary):** The user chose the recommendation: Claude labels each line teacher / student; no on-screen name reading (OCR).

**What the AI did**

- `llm/claude.py`: one structured-output Claude call shared by every AI step (client, retry, refusal, error messages, failure log), pulled out of the judge. `AIUnavailable` replaces `JudgeUnavailable`.
- `llm/roles.py` › `RoleLabeller` + `prompts/roles_v1.md`: Claude Opus 5.5 at low effort returns only the student and media line numbers; every other line is the teacher's. The name check runs before the call.
- Name removal for speech-to-text: a capitalised word mid-sentence that never appears in lowercase is treated as a name (HLD §9.1), plus more non-name words (days, months, languages, chess openings).
- Removed per-student metrics (students present, participation balance, one-to-one): speech-to-text can't tell students apart. Judge prompt v3 explains the automatic roles.
- `scripts/try_roles.py`: Whisper → names → roles on a labelled class, compared line by line with the Zoom speakers. It first checks the pseudonymised text against the local list of real names (`redact_names.txt`) and refuses to call Claude if any is left.
- First run (b516): 1 line still held a known name, so nothing was sent. Diagnosed with a structure-only script (position, case, which rule skipped it; no names or text printed).

| Decision | Why |
|---|---|
| Claude Opus 5.5 at low effort for role labelling | Default model per the Claude API guidance; a cheaper model is the user's call. Low effort fits a simple labelling task |
| Return only student and media line numbers | Short answer; a missed number defaults to teacher, which is the most common role |
| Dev runs check against the full real-name list before any Claude call | `NameGuard` only knows names the pseudonymiser found; the redact list catches what it missed |

**Follow-up prompt (summary):** The user asked whether several people can assess videos at the same time.

| Decision | Why |
|---|---|
| One analysis at a time per server (`analysis_lock`); others wait with a notice and start automatically | Sessions, temp folders and results are already separate, but two Whisper runs at once (~1.2 GB each plus the uploads in memory) could exhaust the ~2.7 GB free host and restart the app for everyone |

**Follow-up prompt (summary):** The user asked whether there is an analysis log.

| Decision | Why |
|---|---|
| One run log (`logs/runs.jsonl`) for analyses and AI calls; `AICallLog` → `RunLog` | One place to see what happened in a run; the app had no record of analyses at all |
| Every log line is also printed | On Streamlit Community Cloud server files vanish on restart; only the app output (Manage app → Logs) is kept |
| `analysis` line: outcome, wait in line, video length, speech-to-text time, line/word counts, total time, peak memory; run id = SHA-256 of the first 1 MB | Gives the real host timings and memory for the deploy test; identifies repeat runs without storing file names; numbers only, no text |

**Privacy check on all 12 recordings (video-only path, counts only, nothing sent to Claude)**

- First scan: 6 of 12 recordings still had lines holding a real name from the local list (55 lines). Structure-only diagnosis (no names or text printed):
  - 3 entries in the real-name list were not names ("italian", "saturday", "tuesday": false entries from when the list was built) → ~30 false alarms.
  - Real misses: names that also appear in lowercase. The rule "any lowercase use = ordinary word" skipped every capitalised use of them.
- Rules compared on the cached transcripts (lines still holding a real name / distinct words replaced): any-lowercase 25 / 352; lowercase > capitals 11 / 411; **never capitalised mid-sentence and lowercase ≥ 2× capitals 2 / 418 (chosen)**; same with an English dictionary 2 / 382 (needs a word list on the host). The 2 lines left are names speech-to-text never capitalises anywhere: documented as residual risk.
- The real-name list builder (`build_redact_list.py`) was reworked for precision: the pseudonymiser's broader rule would have put ordinary words ("lines", "isn" from "Isn't", "goodbye") in the list and blocked 31 files at commit. Now: display names + feedback names + names Zoom capitalises mid-sentence or calls out ("Ishaan, …"), minus common words and their inflections. Result: 485 entries (all 199 real entries of the old list kept, 3 false entries and 4 inflections dropped), 0 repository files blocked.

| Decision | Why |
|---|---|
| Name = capitalised word unless a known non-name or used like a common word (never capitalised mid-sentence, lowercase ≥ 2× capitals) | Measured: leaks 25 → 2 lines across 6 classes, ~7 extra ordinary words replaced per class; no dictionary file needed on the host |
| Contractions ("Isn't") are not name candidates | They split into a capitalised stem ("Isn") that looked like a name |
| Whisper output cached in the private session folder during diagnosis, deleted afterwards | 16 min of Whisper per iteration otherwise; never inside the project or git |

- Final privacy scan, all 12 recordings, rebuilt real-name list: 8 of ~8,700 lines (4 classes) still hold a first name. Cause: 5 names speech-to-text never capitalises anywhere, 1 name used exactly like a common word. Residual risk, decision left to the user.

**Role labelling vs Zoom speakers (3 clean classes; cached Whisper text; Claude Opus 5.5, low effort)**

| Class | Line accuracy | Teacher recall | Student recall | Media recall | Teacher talk (Zoom) | Turn switches/min (Zoom) | Teacher questions/min (Zoom) | Cost, time |
|---|---|---|---|---|---|---|---|---|
| average/b516 | 81% | 471/547 | 105/165 | — | 80% (79%) | 5.3 (5.9) | 2.7 (3.1) | $0.056, 8 s |
| excellent/b472 | 73% | 553/658 | 224/443 | 134/141 | 72% (68%) | 7.4 (10.2) | 2.1 (2.7) | $0.110, 13 s |
| weak/b482 | 79% | 243/267 | 84/147 | — | 80% (74%) | 2.7 (3.6) | 0.8 (1.1) | $0.034, 5 s |

Class-level numbers stay close to Zoom and keep the same order (excellent > average > weak on turn switches). Student lines are missed most: one Whisper segment often holds a teacher question and a child's answer, so it gets one label. Switches/min read 15–30% low for that reason.

**Follow-up prompt (summary):** The user confirmed the output must be one of four grades (Poor / Average / Good / Excellent).

**What the AI did**

- `scoring.py` › `Scorer`: Claude's criterion scores → weighted 0–100 over assessed criteria → grade bands; provisional below 60% assessed. `pipeline.py` › `AssessmentPipeline`: the steps for one recording, shared by the app and `scripts/evaluate.py`. The app now shows the full report (grade, rubric vs Claude's overall view, per-criterion evidence, strengths/improvements, measurements, AI trace).
- `Pseudonymiser(known_names=…)`: names known in advance are always replaced; evaluation passes the local real-name list, so no residual name reaches Claude in development runs.
- First evaluation (transcript only, 10 labelled classes, $2.00): 3/10 exact, 9/10 within one grade; Claude's overall view the same. Details in `eval/results.md`.

| Decision | Why |
|---|---|
| Four grades; weak and known-quality-issue classes count as Poor | The brief asks for four; the HLD label mapping already did this |
| Grade computed in code from criterion scores; Claude's overall view shown beside it | Reproducible and explainable; a two-grade disagreement is flagged |
| Next lever: video and audio checks before tuning bands | Transcript-only scores can't separate Average from Poor; both quality-issue classes fail on screen/connection problems the transcript can't show. Tuning bands on 10 classes would overfit |

**Follow-up prompt (summary):** The user asked how to deploy.

| Decision | Why |
|---|---|
| Upload limit 2 GB → 500 MB | Streamlit holds an upload in memory; with Whisper (~1.2 GB) a 2 GB upload would exceed the ~2.7 GB free host. Samples are 54–340 MB |
| Run log prints first, then writes the file, ignoring write errors | On Streamlit Community Cloud the printed line is what survives; a read-only folder must not break an analysis |
| README rewritten for the video-only pipeline, with deploy steps and how to read real timings from the host log | The old text described an optional transcript upload and a "local-only mode" |

Pre-deploy checks: app boots headless (health endpoint ok, page 200); a dry-run `git add` lists 55 files, none confidential (no media, transcripts, PDFs, logs, caches, `.env`, real-name list), 0 files containing a listed real name, 0 API keys.
