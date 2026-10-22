# ClassLens — Low-Level Design

Companion to [HLD.md](HLD.md). The HLD says **what** the system does and **why**; this document says **where** each part lives in the code and **how** it works: every file, constant, class, field and function, what each takes and returns, the steps inside, who calls it, and how the pieces connect.

**Rule:** the code matches this document. A structural change is made here first, then in code.

Version 2 · 2026-10-22 · Covers everything built in phases 0–2 (ingest, transcript layer, de-identification, metrics, Claude judge). Phases 3–5 are specified as interfaces in §9.

---

## 1. How to read this document

| Section | Answers |
|---|---|
| §2 Code map | Which file holds what; "where is X?" index |
| §3 Architecture views | How modules depend on each other; how data flows through one run |
| §4 Domain model | Every data type passed between modules, field by field |
| §5 Module reference | Per file: constants, classes, every function with signature, steps, calls and callers, and a call graph |
| §6 System call graph | Every function call across modules on one diagram |
| §7 Errors | Every exception: who raises it, who handles it |
| §8 Tests | Which test file covers which module |
| §9 Planned components | Interfaces for phases 3–5 |
| §10 Conventions | Rules the code follows |
| §11 Change log | What changed from v1 and how behaviour was verified |

Notation: `+` public, `_` private (used only inside its own module). "Called by" lists every caller in the repository.

---

## 2. Code map

### 2.1 Files

```
app.py                         Streamlit UI: access gate, uploads, show result             §5.12
classlens/
  __init__.py                  package marker
  config.py                    every setting and threshold; load_env_file()                §5.1
  models.py                    domain dataclasses and enums                                §4
  timecode.py                  seconds ↔ "mm:ss"                                           §5.2
  ingest.py                    save upload, ffprobe (video required)                       §5.3
  asr.py                       Transcriber: local Whisper speech-to-text                   §5.16
  transcript.py                TranscriptParser, TranscriptAnalyzer                        §5.4
  privacy.py                   Pseudonymiser, NameGuard                                    §5.5
  metrics.py                   InteractionAnalyzer                                         §5.6
  runlog.py                    RunLog, estimate_cost(), peak_memory_mb()                   §5.11
  scoring.py                   Scorer: criterion scores → 0–100 → Poor/Average/Good/Excellent §5.18
  pipeline.py                  AssessmentPipeline, Assessment: the steps for one recording   §5.19
  llm/
    __init__.py                package marker
    schema.py                  Pydantic models for Claude's answer                         §5.7
    prompt.py                  PromptBuilder, merge_lines()                                §5.8
    evidence.py                EvidenceValidator, ValidationResult                         §5.9
    claude.py                  StructuredCall, CallStats, AIUnavailable, load_prompt()     §5.10
    judge.py                   ClaudeJudge, JudgeResult                                    §5.10
    roles.py                   RoleLabeller: teacher / student / media per line            §5.17
prompts/judge_v3.md            judge system prompt: rubric, evidence and output rules      §5.14
prompts/roles_v1.md            role-labelling system prompt                                §5.14
scripts/                       local-only tools for the confidential dataset               §5.13
  dataset.py                   Recording, PreparedRecording, iter_recordings(), prepare()
  inspect_transcripts.py       transcript-layer table for all recordings (aggregates)
  try_judge.py                 run Claude on recordings; --dry-run builds payloads only
  try_asr.py                   time Whisper; word recall against the Zoom VTT
  try_roles.py                 Whisper → names → Claude roles, checked against Zoom speakers
  evaluate.py                  full pipeline on the labelled set: grade vs label, confusion matrix
  build_redact_list.py         writes git-ignored redact_names.txt
  check_clean.sh               git pre-commit guard                                         §5.15
tests/                         82 tests on synthetic data                                  §8
docs/HLD.md, docs/LLD.md       design
ai-logs/                       AI interaction history (redacted)
.env.example                   template for the git-ignored .env
.streamlit/config.toml         Streamlit server settings (upload limit 500 MB)
packages.txt                   apt packages for Streamlit Community Cloud (ffmpeg)
requirements.txt               streamlit, anthropic, opencv-python-headless, numpy (pinned)
Dockerfile, .dockerignore      portable container build
```

### 2.2 Where is X?

| I want to find… | File › symbol |
|---|---|
| Any threshold, weight, model name or path | [config.py](../classlens/config.py) |
| The data types passed between modules | [models.py](../classlens/models.py) |
| How an upload is saved and checked | [ingest.py](../classlens/ingest.py) › `save_upload`, `probe` |
| Which uploads are accepted (video only; no audio → provisional) | [ingest.py](../classlens/ingest.py) › `probe`; [config.py](../classlens/config.py) › `VIDEO_EXTENSIONS` |
| How a VTT/SRT file is read | [transcript.py](../classlens/transcript.py) › `TranscriptParser` |
| How the teacher is identified | [transcript.py](../classlens/transcript.py) › `TranscriptAnalyzer.teacher` |
| Transcript quality (good/partial/poor) | [transcript.py](../classlens/transcript.py) › `TranscriptAnalyzer.quality` |
| Whether a clip misses the opening/closing | Claude decides from the transcript: [prompts/judge_v3.md](../prompts/judge_v3.md) (C1 / C5 "not assessed") |
| How names become T / S1 / N1 | [privacy.py](../classlens/privacy.py) › `Pseudonymiser` |
| The check that blocks real names from leaving | [privacy.py](../classlens/privacy.py) › `NameGuard`; used in [llm/prompt.py](../classlens/llm/prompt.py) › `PromptBuilder.build` |
| Talk share, turn-taking, questions… | [metrics.py](../classlens/metrics.py) › `InteractionAnalyzer` |
| Exactly what text is sent to Claude | [llm/prompt.py](../classlens/llm/prompt.py) › `PromptBuilder.build` |
| The rubric Claude scores against | [prompts/judge_v3.md](../prompts/judge_v3.md) |
| Who speaks each line (no Zoom labels) | [llm/roles.py](../classlens/llm/roles.py) › `RoleLabeller`; [prompts/roles_v1.md](../prompts/roles_v1.md) |
| The answer format Claude must return | [llm/schema.py](../classlens/llm/schema.py) › `Judgement` |
| The API call, retry and error handling | [llm/claude.py](../classlens/llm/claude.py) › `StructuredCall` |
| How the grade (Poor / Average / Good / Excellent) is computed | [scoring.py](../classlens/scoring.py) › `Scorer`; [config.py](../classlens/config.py) › `GRADE_BANDS` |
| The order of the steps for one recording | [pipeline.py](../classlens/pipeline.py) › `AssessmentPipeline.run` |
| How accurate the grades are on the labelled set | [scripts/evaluate.py](../scripts/evaluate.py) |
| How made-up quotes are removed | [llm/evidence.py](../classlens/llm/evidence.py) › `EvidenceValidator` |
| Token / cost / latency logging | [runlog.py](../classlens/runlog.py) › `RunLog`, `estimate_cost`, `peak_memory_mb`; [llm/claude.py](../classlens/llm/claude.py) › `CallStats` |
| Access code, upload widget, temp-dir cleanup, the report page | [app.py](../app.py) › `access_granted`, `upload_widget`, `analyse`, `show_result` |
| `.env` loading | [config.py](../classlens/config.py) › `load_env_file` |
| What blocks a commit | [scripts/check_clean.sh](../scripts/check_clean.sh) |

---

## 3. Architecture views

### 3.1 Module dependencies (actual imports)

Arrows point from a module to what it imports. Nothing imports upwards.

```mermaid
flowchart BT
  config[config]
  models[models]
  timecode[timecode]
  ingest[ingest] --> config & models
  asr[asr] --> config & models
  transcript[transcript] --> config & models
  privacy[privacy] --> models
  metrics[metrics] --> config & models
  runlog[runlog] --> config
  schema[llm.schema]
  prompt[llm.prompt] --> config & models & privacy & timecode
  evidence[llm.evidence] --> config & schema & models & timecode
  judge[llm.judge] --> config & runlog & evidence & prompt & schema & models
  app[app.py] --> config & ingest & asr & runlog
  dataset[scripts.dataset] --> ingest & metrics & models & privacy & transcript
  scripts[scripts: inspect / try_judge / try_asr / build_redact_list] --> dataset & privacy & prompt & judge & asr & transcript & config
```

External packages: `streamlit` (app only), `anthropic` + its bundled `pydantic` (llm only), `httpx2` (tests only, ships with `anthropic`). Standard library everywhere else. `ffmpeg`/`ffprobe` are called as programs.

### 3.2 Data flow of one analysis

Boxes are functions; labels on arrows are the data types from §4.

```mermaid
flowchart LR
  raw[/"VTT / SRT text"/] --> P["TranscriptParser.parse"]
  P -- Transcript --> A["TranscriptAnalyzer"]
  A -- TeacherGuess --> PS["Pseudonymiser(teacher).apply"]
  P -- Transcript --> PS
  A -- TranscriptQuality --> PB
  PS -- PseudonymisedTranscript --> M["InteractionAnalyzer.compute"]
  M -- InteractionMetrics --> PB["PromptBuilder.build"]
  PS -- PseudonymisedTranscript --> PB
  media[/"recording file"/] --> PR["ingest.probe"]
  PR -- "MediaInfo (duration)" --> A
  PR -- "MediaInfo (duration)" --> PB
  PB -- "NameGuard.check" --> PB
  PB -- Payload --> J["ClaudeJudge.assess"]
  J -- "Payload.text" --> API[("Claude API")]
  API -- Judgement --> J
  J -- "Judgement + Payload.lines" --> V["EvidenceValidator.validate"]
  V -- ValidationResult --> J
  J -- JudgeResult --> out[/"report (phase 5)"/]
  J -- "metadata only" --> L[("logs/runs.jsonl + printed")]
```

### 3.3 Sequence of one run (today: `scripts/try_judge.py`; phase 4: `AssessmentPipeline`)

```mermaid
sequenceDiagram
  participant R as try_judge.main
  participant D as dataset.prepare
  participant I as ingest.probe
  participant TP as TranscriptParser
  participant TA as TranscriptAnalyzer
  participant PS as Pseudonymiser
  participant IA as InteractionAnalyzer
  participant PB as PromptBuilder
  participant NG as NameGuard
  participant J as ClaudeJudge
  participant C as Claude API
  participant V as EvidenceValidator
  participant L as RunLog
  R->>D: prepare(recording)
  D->>I: probe(video_path)
  I-->>D: MediaInfo
  D->>TP: parse(raw)
  TP-->>D: Transcript
  D->>TA: teacher(), quality(duration)
  D->>PS: Pseudonymiser(teacher).apply(transcript)
  PS-->>D: PseudonymisedTranscript
  D->>IA: InteractionAnalyzer(clean.transcript).compute()
  D-->>R: PreparedRecording
  R->>PB: build(clean, metrics, quality, duration)
  PB->>NG: check(transcript lines + findings)
  PB-->>R: Payload
  R->>J: assess(payload)
  J->>C: beta.messages.parse (up to 2 attempts)
  C-->>J: parsed Judgement + usage
  J->>V: validate(judgement)
  V-->>J: ValidationResult
  J->>L: record("judge", "ok", trace)
  J-->>R: JudgeResult
```

---

## 4. Domain model — [models.py](../classlens/models.py)

Plain data shared by all modules. Frozen dataclasses (immutable) unless noted. No I/O, no analysis.

```mermaid
classDiagram
  direction LR
  class Cue {
    +start: float
    +end: float
    +speaker: str
    +text: str
    +media: bool
    +words: int
  }
  class Transcript {
    +cues: list~Cue~
    +speech() list~Cue~
    +start() float
    +end() float
  }
  class PseudonymisedTranscript {
    +transcript: Transcript
    +name_tokens: frozenset~str~
  }
  class MediaInfo {
    +duration_s: float
    +has_audio: bool
    +width: int
    +height: int
  }
  class TeacherGuess {
    +speaker: str
    +ambiguous: bool
  }
  class QualityLevel {
    <<enum>>
    GOOD
    PARTIAL
    POOR
  }
  class TranscriptQuality {
    +coverage: float
    +words_per_min: float
    +non_latin_share: float
    +level: QualityLevel
  }
  class InteractionMetrics {
    +minutes: float
    +teacher_talk_share: float
    +turn_switches_per_min: float
    +teacher_questions_per_min: float
    +named_question_share: float
    +media_minutes: float
    +long_gaps: int
  }
  class Payload {
    +text: str
    +lines: list~Cue~
  }
  Transcript "1" *-- "many" Cue
  PseudonymisedTranscript "1" *-- "1" Transcript
  Payload "1" *-- "many" Cue
  TranscriptQuality --> QualityLevel
```

### Constants

| Name | Value | Meaning | Used by |
|---|---|---|---|
| `UNKNOWN_SPEAKER` | `"Unknown"` | Speaker of a cue with no label | transcript, privacy, metrics |
| `TEACHER_CODE` | `"T"` | Pseudonymised teacher | privacy, metrics, roles |
| `STUDENT_CODE` | `"S"` | Any student (speech-to-text can't tell students apart) | roles |

### Types

| Type | Field / member | Type | Meaning | Produced by | Consumed by |
|---|---|---|---|---|---|
| **`Cue`** | `start`, `end` | float | Seconds from recording start | `TranscriptParser._parse_block` | everything that reads transcripts |
| | `speaker` | str | Display name (raw) or code `T`/`S1`/`Unknown` (pseudonymised) | parser; `Pseudonymiser.apply` | analyzers, prompt |
| | `text` | str | What was said; names replaced after pseudonymisation | parser; `Pseudonymiser._scrub` | metrics, prompt, evidence |
| | `media` | bool | `True` for `Audio shared by …` cues (a video playing) | `TranscriptParser._extract_speaker` | excluded from speech metrics |
| | `words` (property) | int | Whitespace-separated word count | — | teacher detection, quality, talk share |
| **`Transcript`** | `cues` | list[Cue] | Sorted by `start` | `TranscriptParser.parse`, `Pseudonymiser.apply` | all analyzers |
| | `speech()` | → list[Cue] | Cues with `media=False` | — | `TranscriptAnalyzer`, `InteractionAnalyzer` |
| | `start()` / `end()` | → float | Earliest start / latest end over all cues | — | `InteractionAnalyzer` |
| **`PseudonymisedTranscript`** | `transcript` | Transcript | Coded speakers, scrubbed text | `Pseudonymiser.apply` | `InteractionAnalyzer`, `PromptBuilder` |
| | `name_tokens` | frozenset[str] | Casefolded real-name words; memory only | `Pseudonymiser.apply` | `NameGuard` (via `PromptBuilder`), `build_redact_list` |
| **`MediaInfo`** | `duration_s` | float | Longest duration reported by container/streams | `ingest.probe` | UI, quality, prompt |
| | `has_audio` | bool | Any audio stream (a real video stream is required by `probe`) | `ingest.probe` | UI (no audio → provisional) |
| | `width`, `height` | int \| None | Video size | `ingest.probe` | UI |
| **`TeacherGuess`** | `speaker` | str | Display name, or `Unknown` | `TranscriptAnalyzer.teacher` | `Pseudonymiser` |
| | `ambiguous` | bool | UI should ask the user | same | UI (phase 5), inspect script |
| **`QualityLevel`** | `GOOD`/`PARTIAL`/`POOR` | StrEnum (prints as `good` etc.) | Text-side quality | `TranscriptAnalyzer._quality_level` | prompt, scoring |
| **`TranscriptQuality`** | `coverage` | float \| None | Speech span ÷ recording length (capped at 1); None without recording | `TranscriptAnalyzer.quality` | prompt, scoring |
| | `words_per_min` | float | Spoken words ÷ recording (or speech-span) minutes | same | prompt |
| | `non_latin_share` | float | Share of letters outside ASCII | same | level |
| | `level` | QualityLevel | Rule in §5.4 | same | prompt, scoring |
| **`InteractionMetrics`** | 7 fields | | Defined in §5.6 table | `InteractionAnalyzer.compute` | prompt, scoring |
| **`GradeResult`** | `grade` | str | Poor / Average / Good / Excellent | `Scorer.grade` | report, run log |
| | `score` | float | 0–100 over the assessed criteria | same | report |
| | `assessed_weight` | float | share of the total rubric weight assessed | same | report |
| | `provisional` | bool | assessed weight < `PROVISIONAL_MIN_WEIGHT` | same | report |
| **`Payload`** | `text` | str | The full user message sent to Claude | `PromptBuilder.build` | `ClaudeJudge.assess` |
| | `lines` | list[Cue] | Transcript lines exactly as shown to Claude (merged) | `PromptBuilder.build` | `EvidenceValidator` |

---

## 5. Module reference

### 5.1 [config.py](../classlens/config.py) — settings

Imports: `os`, `pathlib`. Imported by: ingest, transcript, metrics, runlog, llm.prompt, llm.evidence, llm.judge, app, scripts.

#### Constants

| Name | Value | Unit / meaning | Used by |
|---|---|---|---|
| `ROOT` | repo root | Path | `ENV_FILE`, `PROMPTS_DIR`, `RUN_LOG_PATH`, try_judge |
| `ENV_FILE` | `ROOT/.env` | git-ignored secrets file | `load_env_file` default |
| `ACCESS_CODE_ENV` | `"APP_ACCESS_CODE"` | env var name | `app.access_granted` |
| `API_KEY_ENV` | `"ANTHROPIC_API_KEY"` | env var name | `StructuredCall._get_client` |
| `VIDEO_EXTENSIONS` | mp4 mov mkv webm | upload filter | `app.upload_widget` |
| `FFPROBE_TIMEOUT_S` | 60 | seconds | `ingest._run_ffprobe` |
| `WHISPER_MODEL` | `"base"` | faster-whisper model size | `Transcriber._get_model` |
| `WHISPER_THREADS` | 2 | CPU threads (the free host has about 2 cores) | `Transcriber._get_model` |
| `WHISPER_BEAM_SIZE` | 1 | greedy; measured on a 44-min class vs the default 5: 118 s vs 235 s, word recall 0.80 vs 0.82, peak 1.2 GB vs 1.6 GB | `Transcriber._transcribe_window` |
| `WHISPER_WINDOW_S` | 600 | seconds of audio per Whisper call (caps memory) | `Transcriber.transcribe_audio` |
| `CRITERIA` | C1–C7 → (name, weight): Opening and rapport 20 · Individual engagement 25 · Tone and energy 15 · Lesson flow and closure 15 · Homework 10 · Teacher presence and setup 10 · Technical delivery 5 | rubric (HLD §6.1) | `EvidenceValidator` (order, completeness), `Scorer` (weights), report (names) |
| `GRADE_BANDS` | (78, Excellent) · (62, Good) · (48, Average) · (0, Poor) | minimum score per grade; initial, calibrated with `scripts/evaluate.py` | `Scorer._band`, app |
| `PROVISIONAL_MIN_WEIGHT` | 0.6 | share of the rubric weight that must be assessed | `Scorer.grade` |
| `MODEL` | `"claude-opus-5-5"` | Claude model (both calls) | `StructuredCall._send`, `CallStats` |
| `EFFORT` | `"medium"` | reasoning effort | same |
| `MAX_TOKENS` | 16000 | answer token cap | `StructuredCall._send` |
| `AI_MAX_ATTEMPTS` | 2 | one retry | `StructuredCall.run` |
| `FALLBACK_BETA` | `"server-side-fallback-2026-07-01"` | beta flag for refusal fallback | `StructuredCall._send` |
| `PROMPT_VERSION` | `"judge_v3"` | judge prompt file stem | `ClaudeJudge` |
| `ROLES_PROMPT_VERSION` | `"roles_v1"` | role-labelling prompt file stem | `RoleLabeller` |
| `ROLES_EFFORT` | `"low"` | effort for role labelling (simple task) | `RoleLabeller` |
| `PROMPTS_DIR` | `ROOT/prompts` | Path | `load_prompt` |
| `MAX_BLOCK_S` | 60 | seconds; longest merged line | `merge_lines` |
| `EVIDENCE_TOLERANCE_S` | 5 | seconds around a cited timestamp | `EvidenceValidator._lines_near` |
| `EVIDENCE_MIN_MATCH` | 0.8 | share of quote characters that must match | `EvidenceValidator._quote_matches` |
| `RUN_LOG_PATH` | `ROOT/logs/runs.jsonl` | git-ignored run log (also printed) | `RunLog.record` |
| `PRICE_PER_MTOK` | input 4.0 · output 20.0 · cache_write 5.0 · cache_read 0.20 | USD per million tokens | `estimate_cost` |
| `OPENING_WINDOW_MIN` | 10 | minutes | `PromptBuilder._transcript_section` |
| `CLOSING_WINDOW_MIN` | 10 | minutes | `PromptBuilder._transcript_section` |
| `TEACHER_AMBIGUITY_MARGIN` | 0.10 | share of top speaker's words | `TranscriptAnalyzer.teacher` |
| `LONG_GAP_S` | 20 | seconds | `InteractionAnalyzer._long_gaps`, prompt text |
| `QUALITY_GOOD_COVERAGE` / `QUALITY_POOR_COVERAGE` | 0.8 / 0.5 | share | `TranscriptAnalyzer._quality_level` |
| `QUALITY_GOOD_WPM` / `QUALITY_POOR_WPM` | 60 / 25 | words per minute | same |
| `QUALITY_MAX_NON_LATIN` | 0.3 | share of letters | same |

#### Functions

| Signature | Does | Called by |
|---|---|---|
| `load_env_file(path: Path = ENV_FILE) -> None` | Reads `KEY=VALUE` lines (comments, quotes and `export ` prefix allowed) into `os.environ` with `setdefault`, so real environment variables win. Missing file → no-op. | `app.main`, `try_judge.main` |

---

### 5.2 [timecode.py](../classlens/timecode.py) — timestamps

| Name | Kind | Signature / value | Does | Called by |
|---|---|---|---|---|
| `TIMESTAMP` | regex | `(\d{1,2}):(\d{2})(?::(\d{2}))?` | Matches `12:31`, `1:02:05` | `parse_time` |
| `format_time` | function | `(seconds: float) -> str` | 65 → `"01:05"`; 3725 → `"1:02:05"` | `llm.prompt._render` |
| `parse_time` | function | `(text: str) -> float \| None` | First timestamp in text → seconds; two parts = mm:ss, three = h:mm:ss; none → `None` | `EvidenceValidator._lines_near` |

---

### 5.3 [ingest.py](../classlens/ingest.py) — inputs

Imports: config, models. Imported by: app, scripts.dataset, scripts.try_asr.

| Name | Kind | Value / signature | Meaning |
|---|---|---|---|
| `COPY_CHUNK_BYTES` | const | 8 MiB | Copy buffer for uploads |
| `RUN_ID_BYTES` | const | 1 MiB | How much of the file `run_id` hashes |
| `IngestError` | exception | `Exception` subclass | Bad input; message shown to the user as-is |

| Function | Signature | Returns / raises | Steps | Calls | Called by |
|---|---|---|---|---|---|
| `run_id` | `(path: Path) -> str` | 12 hex chars | SHA-256 of the first `RUN_ID_BYTES` (1 MiB): same video → same id, no file name stored | `hashlib` | `app.analyse` |
| `save_upload` | `(upload, original_name: str, workdir: Path) -> Path` (upload: any binary file object) | Path of `input.<ext>` | Stream-copy the upload under a generic name (original names can contain personal names) | `shutil.copyfileobj` | `app.analyse` |
| `probe` | `(path: Path) -> MediaInfo` | MediaInfo · raises `IngestError` | 1 `_run_ffprobe` → JSON · 2 `_real_video_stream` · 3 any audio stream? · 4 `_duration` · 5 reject zero length or no video | `_run_ffprobe`, `_real_video_stream`, `_duration` | `app.analyse`, `dataset.prepare` |
| `_run_ffprobe` | `(path: Path) -> dict` | parsed JSON · raises `IngestError` on non-zero exit or timeout | `ffprobe -v error -print_format json -show_format -show_streams` | `subprocess.run` | `probe` |
| `_real_video_stream` | `(streams: list[dict]) -> dict \| None` | first video stream that isn't cover art (`disposition.attached_pic`) | loop | — | `probe` |
| `_duration` | `(data: dict) -> float` | max of format and stream durations, ignoring missing/`N/A`; 0.0 if none | list → max | — | `probe` |

```mermaid
flowchart LR
  probe --> _run_ffprobe & _real_video_stream & _duration
  app.analyse --> save_upload & probe
  dataset.prepare --> probe
```

---

### 5.4 [transcript.py](../classlens/transcript.py) — reading and structure

Imports: config, models. Imported by: scripts.dataset (phase 4: pipeline).

`TranscriptParser` reads the Zoom VTTs of the labelled set (offline scripts only); in the app the transcript comes from local speech-to-text (`asr.py` › `Transcriber`). `TranscriptAnalyzer` works on either.

#### Constants

| Name | Pattern / value | Example match | Used in |
|---|---|---|---|
| `_STAMP` | `(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}` | `00:01:02.500`, `01:02,500` | `TIMING` |
| `TIMING` | `(_STAMP)\s*-->\s*(_STAMP)` | `00:01:02.500 --> 00:01:04.000 align:start` | `_parse_timing` |
| `VOICE_TAG` | `^<v(?:\.[^\s>]*)?\s+([^>]+)>` | `<v Priya Rao>Hello` → `Priya Rao` | `_extract_speaker` |
| `ANY_TAG` | `<[^>]+>` | `<i>`, `</v>` | `_extract_speaker` |
| `SPEAKER_PREFIX` | `^([^:]{1,40}?):\s+(.+)$` | `Priya Rao: Hello` (not `10:30 is…`) | `_extract_speaker` |
| `BLOCK_SEPARATOR` | `\n\s*\n` | blank line | `_split_blocks` |
| `MEDIA_PREFIX` | `"audio shared by "` | `Audio shared by Priya Rao: …` | `_extract_speaker` |

#### Classes

```mermaid
classDiagram
  class TranscriptParser {
    +parse(raw: str) Transcript
    -_normalise(raw: str) str
    -_split_blocks(text: str) list~str~
    -_parse_block(block: str) Cue
    -_parse_timing(line: str) tuple
    -_extract_speaker(text: str) tuple
  }
  class TranscriptAnalyzer {
    +transcript: Transcript
    +speech: list~Cue~
    +teacher() TeacherGuess
    +quality(duration_s) TranscriptQuality
    -_words_by_speaker() dict
    -_hosts() set
    -_speech_span() tuple
    -_coverage(duration_s) float
    -_words_per_minute(duration_s) float
    -_non_latin_share() float
    -_quality_level(coverage, wpm, non_latin) QualityLevel
  }
  TranscriptParser ..> Transcript : creates
  TranscriptAnalyzer --> Transcript : reads
  TranscriptAnalyzer ..> TeacherGuess : creates
  TranscriptAnalyzer ..> TranscriptQuality : creates
```

**`TranscriptParser`** (no state)

| Method | Signature | Returns | Steps / rule | Calls | Called by |
|---|---|---|---|---|---|
| `parse` | `(raw: str) -> Transcript` | Transcript, cues sorted by start | 1 `_normalise` · 2 `_split_blocks` · 3 `_parse_block` each, skip `None` · 4 sort | the three below | `dataset.prepare` |
| `_normalise` | `(raw) -> str` | text | strip BOM `﻿`, CRLF → LF | — | `parse` |
| `_split_blocks` | `(text) -> list[str]` | blocks | split on `BLOCK_SEPARATOR` | — | `parse` |
| `_parse_block` | `(block) -> Cue \| None` | Cue, or None for header/NOTE/STYLE/empty | 1 find first line matching `TIMING` (none → None) · 2 join following lines with spaces · 3 `_extract_speaker` · 4 empty text → None | `_parse_timing`, `_extract_speaker` | `parse` |
| `_parse_timing` | `(line) -> tuple[float, float] \| None` | (start, end) seconds | `TIMING.search` → `_to_seconds` ×2 | `_to_seconds` | `_parse_block` |
| `_extract_speaker` | `(text) -> tuple[str, str, bool]` | (speaker, text, media) | 1 `VOICE_TAG` → speaker · 2 remove `ANY_TAG` · 3 if still Unknown: `SPEAKER_PREFIX` → speaker + text · 4 speaker starts with `MEDIA_PREFIX` → strip it, media=True | — | `_parse_block` |

Module function `_to_seconds(stamp: str) -> float` — `"01:02:03.250"` → 3723.25 (accepts `,`), adding seconds, minutes, hours in that order. Called by `_parse_timing`.

**`TranscriptAnalyzer(transcript)`** — fields: `transcript`, `speech` (= `transcript.speech()`, computed once)

| Method | Signature | Returns | Rule | Calls | Called by |
|---|---|---|---|---|---|
| `teacher` | `() -> TeacherGuess` | speaker, ambiguous | 1 words per speaker (media, Unknown excluded) · 2 none → (Unknown, ambiguous) · 3 one speaker → them · 4 top − second ≥ 10% of top → top · 5 exactly one of top two is a host → host · 6 else top, ambiguous | `_words_by_speaker`, `_hosts` | `dataset.prepare` |
| `quality` | `(duration_s: float \| None) -> TranscriptQuality` | coverage, wpm, non-Latin, level | no speech → POOR · else compute the three signals → `_quality_level` | `_coverage`, `_words_per_minute`, `_non_latin_share`, `_quality_level` | `dataset.prepare` |
| `_words_by_speaker` | `() -> dict[str, int]` | speaker → words | loop over speech, skip Unknown | — | `teacher` |
| `_hosts` | `() -> set[str]` | speakers with any media cue | Zoom only lets the host share audio | — | `teacher` |
| `_speech_span` | `() -> tuple[float, float]` | (first speech start, last speech end) | — | — | `_coverage`, `_words_per_minute` |
| `_coverage` | `(duration_s) -> float \| None` | span ÷ duration, max 1; None without duration | — | `_speech_span` | `quality` |
| `_words_per_minute` | `(duration_s) -> float` | words ÷ minutes (recording length, else span); 0 if no time | — | `_speech_span` | `quality` |
| `_non_latin_share` | `() -> float` | non-ASCII letters ÷ letters | — | — | `quality` |
| `_quality_level` | `(coverage, words_per_min, non_latin) -> QualityLevel` | level | POOR if coverage < 0.5, wpm < 25 or non-Latin > 0.3 · PARTIAL if coverage < 0.8 or wpm < 60 · else GOOD | — | `quality` |

```mermaid
flowchart LR
  parse --> _normalise & _split_blocks & _parse_block
  _parse_block --> _parse_timing & _extract_speaker
  _parse_timing --> _to_seconds
  teacher --> _words_by_speaker & _hosts
  quality --> _coverage & _words_per_minute & _non_latin_share & _quality_level
  _coverage & _words_per_minute --> _speech_span
```

---

### 5.5 [privacy.py](../classlens/privacy.py) — de-identification

Imports: models. Imported by: llm.prompt, scripts.dataset, scripts.inspect_transcripts, scripts.build_redact_list.

#### Constants

| Name | Value / pattern | Example | Used in |
|---|---|---|---|
| `LABEL_NOISE` | device, role and placeholder words: iphone, ipad, android, galaxy, samsung, redmi, oppo, vivo, realme, oneplus, pixel, laptop, desktop, macbook, phone, mobile, tablet, user, guest, zoom, demo, class, host, admin, teacher, trainer, coach, student, test | "Zoya's **iPhone**" | `display_name_tokens`, `_is_ordinary_word` |
| `NOT_NAMES` | ~95 common classroom words (actually, again, board, bye, camera, chess, everyone, good, homework, king, knight, okay, puzzle, sir, today, video, yes…) + words speech-to-text capitalises that aren't people (days, months, languages, India, YouTube, Lichess, Sicilian, Gambit, chess pieces, goodbye…) + sentence starters (pronouns, helper verbs) | "**Okay**, …" | `_is_ordinary_word` |
| `CAPITALISED_WORD` | `\b[A-Z][a-z]{2,}\b(?![’']t\b)`: any capitalised word of 3+ letters, wherever it is, except a contraction | "Hello **Ishaan**", "ask **Ishaan**", "**Ravi**." (not "Isn't") | `_find_spoken_names`, `_word_counts` |
| `EMAIL` | `\b[\w.+-]+@[\w-]+\.[\w.]+\b` | `tara.q@example.com` | `_scrub` |
| `PHONE` | `\+?\d[\d\s-]{8,}\d` | `+91 98765 43210` | `_scrub` |
| `POSSESSIVE` | `[’']s\b` | "Priya**’s** iPhone" | `display_name_tokens` |
| `LETTER_RUN` | `[^\W\d_]+` | `__ISHAAN__MEHRA__` → ISHAAN, MEHRA | `display_name_tokens` |
| `LOWERCASE_WORD` | `\b[a-z]+\b` | "the **bishop** moves" | `_word_counts` |
| `REPEATED_CODE` | `\b([TSN]\d*)(?:\s+\1\b)+` | `T T` → `T` | `_scrub` |
| `MIN_NAME_LENGTH` | 3 | — | `display_name_tokens` |
| `PrivacyError` | exception | — | raised by `NameGuard.check` |

#### Module functions

| Signature | Returns | Rule | Called by |
|---|---|---|---|
| `display_name_tokens(label: str) -> list[str]` | casefolded name words | remove possessive → split into letter runs → keep length ≥ 3 and not in `LABEL_NOISE`. "Priya’s iPhone" → `["priya"]` | `Pseudonymiser._map_label_names`, `build_redact_list.feedback_names` |
| `names_pattern(tokens) -> re.Pattern \| None` | one case-insensitive whole-word regex, longest token first; None if empty | — | `Pseudonymiser.apply`, `NameGuard.__init__` |

#### Classes

```mermaid
classDiagram
  class Pseudonymiser {
    +teacher: str
    +apply(transcript) PseudonymisedTranscript
    -_assign_speaker_codes(transcript) dict
    -_map_label_names(speaker_codes) dict
    -_find_spoken_names(transcript, known) dict
    -_word_counts(transcript) tuple
    -_is_ordinary_word(word, mid_sentence, sentence_start, lowercase) bool
    -_scrub(text, name_codes, pattern) str
  }
  class NameGuard {
    -_pattern: Pattern
    +check(text) None
  }
  class PrivacyError
  Pseudonymiser ..> PseudonymisedTranscript : creates
  NameGuard ..> PrivacyError : raises
  Pseudonymiser ..> names_pattern : uses
  NameGuard ..> names_pattern : uses
  Pseudonymiser ..> display_name_tokens : uses
```

**`Pseudonymiser(teacher: str, known_names: frozenset[str] = frozenset())`** — fields `teacher` (display name from `TeacherGuess`; `Unknown` for speech-to-text) and `known_names` (casefolded names always replaced even if no rule finds them; evaluation passes the local real-name list)

| Method | Signature | Returns | Steps / rule | Calls | Called by |
|---|---|---|---|---|---|
| `apply` | `(transcript: Transcript) -> PseudonymisedTranscript` | coded transcript + name tokens | 1 `_assign_speaker_codes` · 2 `_map_label_names` · 3 add `_find_spoken_names` · 3b add `_code_known_names` · 4 `names_pattern` · 5 for each cue: speaker → code (unknown → Unknown), text → `_scrub` | all below | `dataset.prepare` |
| `_assign_speaker_codes` | `(transcript) -> dict[str, str]` | display name → `T`/`S1`… | teacher → T (unless teacher is Unknown) · others → S1, S2… in order of first appearance · Unknown not coded | — | `apply` |
| `_map_label_names` | `(speaker_codes) -> dict[str, str]` | name token → code | pass 1: first token of each display name; pass 2: remaining tokens; `setdefault`, so a shared surname never overrides a first name | `display_name_tokens` | `apply` |
| `_find_spoken_names` | `(transcript, known) -> dict[str, str]` | token → `N1`, `N2`… | `_word_counts` · for each `CAPITALISED_WORD`: skip if known/found or `_is_ordinary_word` · else next N code. **When unsure, treat as a name**: a rare word at a sentence start may be replaced too | `_word_counts`, `_is_ordinary_word` | `apply` |
| `_word_counts` | `(transcript) -> (mid_sentence, sentence_start, lowercase)` | per casefolded word: times capitalised mid-sentence, capitalised at a sentence start (line start or after `.?!`), written in lowercase | — | `_find_spoken_names`, `build_redact_list` |
| `_is_ordinary_word` | `(word, mid_sentence, sentence_start, lowercase) -> bool` | — | in `NOT_NAMES` or `LABEL_NOISE`, or never capitalised mid-sentence and written in lowercase at least twice as often as capitalised. Measured on 6 real classes: "any lowercase use = ordinary" left names in 25 lines, this rule in 2 (names never capitalised anywhere) | — | `_find_spoken_names` |
| `_code_known_names` | `(coded) -> dict[str, str]` | known name → next N code | `known_names` not already coded, sorted, numbered after the spoken names | — | `apply` |
| `_scrub` | `(text, name_codes, pattern) -> str` | clean text | emails → `[email]` · phones → `[phone]` · name tokens → codes · `REPEATED_CODE` collapse | — | `apply` |

**`NameGuard(name_tokens: frozenset[str])`** — field `_pattern` (from `names_pattern`)

| Method | Signature | Rule | Called by |
|---|---|---|---|
| `check` | `(text: str) -> None` | raises `PrivacyError` if any token appears; no tokens → always passes | `PromptBuilder.build`, `RoleLabeller.label`, `inspect_transcripts.guard_status` |

```mermaid
flowchart LR
  apply --> _assign_speaker_codes & _map_label_names & _find_spoken_names & names_pattern & _scrub
  _map_label_names --> display_name_tokens
  _find_spoken_names --> _word_counts & _is_ordinary_word
  NameGuard.__init__ --> names_pattern
```

---

### 5.6 [metrics.py](../classlens/metrics.py) — interaction metrics

Imports: config, models. Imported by: scripts.dataset, tests.

#### Constants

| Name | Pattern / value | Example | Used in |
|---|---|---|---|
| `NAMED_PERSON` | `\b[SN]\d+\b` | "**N1**, your move" (or "**S3**" in a Zoom VTT) | `_named_question_share` |
| `MIN_MINUTES` | 1/60 | avoids dividing by zero | `__init__` |

**`InteractionAnalyzer(transcript: Transcript)`** — input is the **pseudonymised** transcript.

| Field (set in `__init__`) | Value |
|---|---|
| `transcript` | the input |
| `speech` | speech cues with a known speaker (raises `ValueError` if empty) |
| `teacher_cues` | speech cues by `T` |
| `students` | sorted set of non-`T` speakers |
| `minutes` | (transcript end − start) ÷ 60, at least `MIN_MINUTES` |

| Method | Returns | Definition | Feeds field |
|---|---|---|---|
| `compute()` | InteractionMetrics | calls every helper below | all |
| `_teacher_talk_share()` | float | teacher words ÷ all speech words | `teacher_talk_share` |
| `_turn_switches()` | int | consecutive speech cues where one is `T` and the other isn't | `turn_switches_per_min` (÷ minutes) |
| `_teacher_questions()` | list[Cue] | teacher cues containing `?` | `teacher_questions_per_min` |
| `_named_question_share(questions)` | float | questions containing `NAMED_PERSON` ÷ questions | `named_question_share` |
| `_media_minutes()` | float | total duration of media cues | `media_minutes` |
| `_long_gaps()` | int | gaps > 20 s between consecutive speech cues | `long_gaps` |

Called by: `dataset.prepare`, `tests/fakes.py`.

---

### 5.7 [llm/schema.py](../classlens/llm/schema.py) — Claude's answer format

Pydantic models; the SDK converts `RoleLabels` / `Judgement` to a JSON schema and validates the answer against it.

| Type | Field | Type | Meaning |
|---|---|---|---|
| **`RoleLabels`** | `student_lines` | list[int] | numbered lines spoken by a child (or a parent for one) |
| | `media_lines` | list[int] | numbered lines of recorded audio (e.g. a shared chess video) |

Every line in neither list is the teacher's.

| Type | Field | Type | Meaning |
|---|---|---|---|
| `CriterionId` | — | `Literal["C1"…"C7"]` | rubric ids (HLD §6.1) |
| `Grade` | — | `Literal["Poor","Average","Good","Excellent"]` | holistic grade |
| **`Evidence`** | `timestamp` | str | `mm:ss` / `h:mm:ss` of a transcript line |
| | `quote` | str | short exact quote from that line |
| | `observation` | str | what it shows |
| | `polarity` | positive \| negative | |
| **`CriterionAssessment`** | `criterion_id` | CriterionId | |
| | `assessed` | bool | false when the input can't show it |
| | `score` | 1–4 \| None | None when not assessed |
| | `rationale` | str | reasoning or why not assessed |
| | `evidence` | list[Evidence] | |
| **`Point`** | `criterion_id`, `timestamp`, `text` | | a strength or improvement tied to a moment |
| **`Judgement`** | `criteria` | list[CriterionAssessment] | |
| | `strengths`, `improvements` | list[Point] | |
| | `holistic_grade` | Grade | Claude's overall view (compared with the computed grade later) |
| | `transcript_quality` | good \| partial \| poor | Claude's reading of the transcript |
| | `summary` | str | 2–3 sentences |

---

### 5.8 [llm/prompt.py](../classlens/llm/prompt.py) — building the payload

Imports: config, models, privacy (`NameGuard`), timecode. Imported by: llm.judge, scripts.try_judge, tests.

| Function | Signature | Does | Called by |
|---|---|---|---|
| `merge_lines` | `(transcript: Transcript) -> list[Cue]` | consecutive cues by the same speaker → one line while it spans ≤ 60 s; a run of media cues → one line however long | `PromptBuilder.build` |
| `_phase` | `(start, opening_end, closing_start) -> str` | `OPENING` / `CLOSING` / `MAIN` | `_transcript_section` |
| `_render` | `(line: Cue) -> str` | `[12:31] T: text` or `[00:30] (shared audio or video playing until 06:40)` | `_transcript_section` |

**`PromptBuilder(findings: list[str] | None = None)`** — field `findings`: video/audio facts as sentences (empty until phase 3).

| Method | Signature | Returns | Steps | Called by |
|---|---|---|---|---|
| `build` | `(clean, metrics, quality, duration_s) -> Payload` | Payload · raises `PrivacyError` | 1 `merge_lines` · 2 `_transcript_section` · 3 **`NameGuard(clean.name_tokens).check`** on transcript lines + findings · 4 join sections · 5 `Payload(text, lines)` | `try_judge.main`, tests |
| `_recording_section` | `(metrics, quality, duration_s) -> list[str]` | lines | `RECORDING`: length, text quality + wpm | `build` |
| `_metrics_section` | `(metrics) -> list[str]` | lines | `MEASURED INTERACTION`: talk share, switches/min, questions/min + named %, media minutes, long silences | `build` |
| `_findings_section` | `() -> list[str]` | lines | `VIDEO AND AUDIO FINDINGS`: one line per finding, or "Not analysed for this run." | `build` |
| `_transcript_section` | `(lines) -> list[str]` | lines | phase marker whenever the phase changes, then `_render` per line | `build` |

Payload layout (exact order):

```
RECORDING
- Length: 54 min
- Transcript quality from text signals: good (104 words/min)

MEASURED INTERACTION
- Teacher share of spoken words: 69%
- Teacher/student turn switches: 11.7 per min
- Teacher questions: 3.2 per min (16% name someone)
- Shared media played: 0.0 min; silences over 20 s: 2

VIDEO AND AUDIO FINDINGS
- Not analysed for this run.

<transcript>
=== OPENING ===
[00:21] T: Hello S1!
…
=== MAIN ===
…
=== CLOSING ===
…
</transcript>
```

```mermaid
flowchart LR
  build --> merge_lines & _transcript_section & NameGuard.check & _recording_section & _metrics_section & _findings_section
  _transcript_section --> _phase & _render
  _render --> format_time
```

---

### 5.9 [llm/evidence.py](../classlens/llm/evidence.py) — grounding check

Imports: config, llm.schema, models, timecode. Imported by: llm.judge.

| Name | Kind | Value | Meaning |
|---|---|---|---|
| `NON_WORD` | regex | `[^\w\s]` | punctuation removed before comparing |
| `MIN_MATCH_RUN` | const | 4 | shorter matching runs are coincidences |
| `ValidationResult` | dataclass | `judgement: Judgement`, `counts: dict[str, tuple[int, int]]` | checked answer; per criterion (accepted, rejected) |
| `_normalise` | function | `(text) -> str` | casefold, punctuation → space, collapse spaces |

**`EvidenceValidator(lines: list[Cue])`** — field `lines` = `Payload.lines`

| Method | Signature | Returns | Rule | Calls | Called by |
|---|---|---|---|---|---|
| `validate` | `(judgement) -> ValidationResult` | checked judgement + counts | 1 for each criterion (first answer per id wins) `_check_criterion` · 2 `_add_missing` · 3 order criteria as in `CRITERIA` · 4 `_grounded_points` for strengths and improvements | below | `ClaudeJudge.assess` |
| `_check_criterion` | `(item) -> (CriterionAssessment, (accepted, rejected))` | | keep evidence where `_is_grounded`; `assessed` only if a score is present; score cleared when not assessed | `_is_grounded` | `validate` |
| `_add_missing` | `(criteria, counts) -> None` | | any id from `CRITERIA` not returned → not assessed, "Not returned by the AI model." | — | `validate` |
| `_grounded_points` | `(points) -> list[Point]` | | keep points whose timestamp hits a spoken line | `_lines_near` | `validate` |
| `_is_grounded` | `(evidence) -> bool` | | some line near the timestamp `_quote_matches` | `_lines_near`, `_quote_matches` | `_check_criterion` |
| `_lines_near` | `(timestamp: str) -> list[Cue]` | | `parse_time`; spoken (non-media) lines whose [start − 5 s, end + 5 s] contains it | `parse_time` | `_is_grounded`, `_grounded_points` |
| `_quote_matches` | `(quote, line_text) -> bool` | | normalise both · contained → True · else `SequenceMatcher` matching runs of ≥ 4 chars cover ≥ 80% of the quote | `_normalise` | `_is_grounded` |

```mermaid
flowchart LR
  validate --> _check_criterion & _add_missing & _grounded_points
  _check_criterion --> _is_grounded
  _is_grounded --> _lines_near & _quote_matches
  _grounded_points --> _lines_near
  _lines_near --> parse_time
  _quote_matches --> _normalise
```

---

### 5.10 [llm/claude.py](../classlens/llm/claude.py) and [llm/judge.py](../classlens/llm/judge.py) — Claude calls

`claude.py` imports: anthropic, config, runlog. Imported by: llm.judge, llm.roles. `judge.py` imports: config, runlog, llm.claude, llm.evidence, llm.schema, models. Imported by: scripts.try_judge (phase 4: pipeline).

| Name | Kind | Fields / members |
|---|---|---|
| `load_prompt` | function | `(version: str) -> str`: reads `prompts/<version>.md` |
| `AIUnavailable` | exception | user-facing message; caller falls back to local-only mode |
| `CallStats` | mutable dataclass | `prompt_version`, `effort` (required) · `model` (config) · `attempts`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_s` (accumulated) · `served_model`, `stop_reason` (last response) · `add_response(response, seconds)` · `as_dict()` |
| `unavailable` | function | `(error: anthropic.APIError) -> AIUnavailable`, most specific first: 401 "key was rejected" · 429 "rate-limited" · other status "returned an error (code)" · connection "Could not reach" · else "call failed" |
| `JudgeResult` | dataclass (judge.py) | `judgement` (validated), `evidence_counts`, `trace` (CallStats fields + evidence_accepted, evidence_rejected, holistic_grade, transcript_quality) |

```mermaid
classDiagram
  class StructuredCall {
    +purpose: str
    +prompt_version: str
    +effort: str
    +log: RunLog
    -_client
    +run(user_text, output_format) tuple
    -_get_client()
    -_send(client, system, user_text, output_format)
  }
  class ClaudeJudge {
    -_call: StructuredCall
    +assess(payload) JudgeResult
    -_trace(stats, validation) dict
  }
  class RoleLabeller {
    -_call: StructuredCall
    +label(clean) PseudonymisedTranscript
  }
  ClaudeJudge --> StructuredCall : uses
  RoleLabeller --> StructuredCall : uses
  StructuredCall --> CallStats : accumulates
  StructuredCall ..> AIUnavailable : raises
  ClaudeJudge --> EvidenceValidator : validates with
  ClaudeJudge ..> JudgeResult : returns
```

**`StructuredCall(purpose, prompt_version, effort, client=None, log=None)`** — one structured-output call shared by every AI step. `_client`: injected in tests, else created from `ANTHROPIC_API_KEY`; `log`: defaults to `RunLog()`. Logs failures itself; callers log their own "ok" entry.

| Method | Signature | Returns / raises | Steps | Called by |
|---|---|---|---|---|
| `run` | `(user_text, output_format) -> (parsed, CallStats)` | · `AIUnavailable` | `load_prompt(prompt_version)` · up to `AI_MAX_ATTEMPTS`: `_send` · `ValueError` (bad/truncated JSON) → retry · `anthropic.APIError` → `unavailable` · refusal → log + raise · `max_tokens` or no parsed output → retry · else return. All attempts used → log "unreadable" + raise | `ClaudeJudge.assess`, `RoleLabeller.label` |
| `_get_client` | `()` | client · `AIUnavailable` if no key | lazy `anthropic.Anthropic()` | `run` |
| `_send` | `(client, system, user_text, output_format)` | SDK response | `client.beta.messages.parse(model=MODEL, max_tokens=MAX_TOKENS, system=[prompt, cache_control ephemeral], messages=[user_text], output_format=…, output_config={effort}, betas=[FALLBACK_BETA], fallbacks="default")` | `run` |

**`ClaudeJudge(client=None, log=None)`** — `_call = StructuredCall("judge", PROMPT_VERSION, EFFORT, …)`.

| Method | Signature | Returns / raises | Steps | Called by |
|---|---|---|---|---|
| `assess` | `(payload: Payload) -> JudgeResult` | JudgeResult · `AIUnavailable` | 1 `_call.run(payload.text, Judgement)` · 2 `EvidenceValidator(payload.lines).validate` · 3 `_trace` · 4 log `("judge", "ok", trace)` | `try_judge.main` |
| `_trace` | `(stats, validation) -> dict` | | `stats.as_dict()` + evidence totals + holistic grade + transcript quality | `assess` |

```mermaid
flowchart LR
  assess --> StructuredCall.run & EvidenceValidator.validate & _trace & RunLog.record
  label[RoleLabeller.label] --> StructuredCall.run
  StructuredCall.run --> load_prompt & _get_client & _send & unavailable & CallStats.add_response & RunLog.record
  CallStats.add_response --> estimate_cost
```

---

### 5.11 [runlog.py](../classlens/runlog.py) — runtime log

Imports: `json`, `resource`, `sys`, config. Imported by: llm.claude, llm.judge, llm.roles, app, scripts, tests.

| Member | Signature | Does | Called by |
|---|---|---|---|
| `estimate_cost` | `(usage) -> float` | USD = Σ tokens × `PRICE_PER_MTOK` ÷ 1e6 over input, output, cache_write, cache_read (missing cache fields = 0) | `CallStats.add_response` |
| `peak_memory_mb` | `() -> float` | highest memory use of this process so far (`ru_maxrss`: bytes on macOS, KiB on Linux) | `app.run_analysis`, `try_asr` |
| `RunLog.__init__` | `(path: Path \| None = None)` | `None` → `config.RUN_LOG_PATH`, read at write time | `StructuredCall`, `app.run_analysis` |
| `RunLog.record` | `(purpose: str, outcome: str, fields: dict) -> None` | prints `{"ts", "purpose", "outcome", **fields}` as one JSON line **and appends it to the file** (creates the folder; a write error is ignored), because on Streamlit Community Cloud only the app's output (Manage app → Logs) survives a restart | `app.run_analysis`, `ClaudeJudge.assess`, `RoleLabeller.label`, `StructuredCall.run` |

Purposes and outcomes written today:

| Purpose | Outcomes | Fields |
|---|---|---|
| `analysis` | `ok`, `rejected` (`IngestError`), `error` (+ exception type only) | `run_id`, `waited_s`, `video_min`, `has_audio`, `transcription_s`, `lines`, `words`, `total_s`, `peak_memory_mb` (whatever was reached before a failure) |
| `roles` | `ok`, `refusal`, `unreadable` | `CallStats` fields + `lines`, `student_lines`, `media_lines` |
| `judge` | `ok`, `refusal`, `unreadable` | `CallStats` fields + evidence accepted/rejected, holistic grade, transcript quality |

Never contains transcript text, names or file names (asserted by `test_judge.py`; file names never reach the log).

---

### 5.12 [app.py](../app.py) — Streamlit UI

Imports: streamlit, config, ingest. Streamlit re-runs the script top to bottom on every interaction; `main()` is called at module level.

| Session-state key | Meaning |
|---|---|
| `authorised` | access code accepted |
| `upload_round` | counter in the uploader keys; incrementing it drops uploaded files from memory |
| `result` | last analysis result, shown after the re-run |

| Function | Signature | Does | Calls | Called by |
|---|---|---|---|---|
| `main` | `() -> None` | page config · `load_env_file` · title · gate (`st.stop()` if not granted) · data notice · `upload_widget` · Analyse button → `run_analysis` · `show_result` if a result exists | below | module level |
| `access_granted` | `() -> bool` | no `APP_ACCESS_CODE` → True (local dev) · already authorised → True · password field, constant-time compare (`hmac.compare_digest`) · wrong → error | — | `main` |
| `upload_widget` | `() -> UploadedFile \| None` | one `st.file_uploader` for `VIDEO_EXTENSIONS`, keyed by `upload_round` | — | `main` |
| `analysis_lock` | `() -> threading.Lock` | `@st.cache_resource`: one lock shared by every session, so only one analysis runs at a time | — | `run_analysis` |
| `run_analysis` | `(recording) -> None` | `analysis_lock` busy → `BUSY_NOTICE`, wait · `st.status` (label updated by each pipeline step) → `analyse` → store result, bump `upload_round`, rerun · `IngestError` → show message, clear result · other exception → record its type, re-raise · `finally`: release the lock, add `total_s` + `peak_memory_mb`, `RunLog().record("analysis", ok/rejected/error, facts)` | `analysis_lock`, `analyse`, `RunLog.record` | `main` |
| `pipeline` | `() -> AssessmentPipeline` | `@st.cache_resource`: one Whisper model and one Claude client per server process, created on the first analysis | `AssessmentPipeline`, `Transcriber` | `analyse` |
| `analyse` | `(recording, facts: dict, on_step) -> dict` | inside `TemporaryDirectory` (always deleted): `save_upload` → `run_id` → `pipeline().run(path, facts, on_step)`; returns `{"assessment"}`. Facts fill as the steps run, so the run log has them even if a later step fails | `save_upload`, `run_id`, `AssessmentPipeline.run` | `run_analysis` |
| `show_result` | `(result: dict) -> None` | no grade → the note + measurements; else `show_grade`, `show_criteria`, `show_points`, `show_measurements`, `show_trace` | below | `main` |
| `show_grade` | `(assessment)` | grade heading; rubric score and the AI's overall view; warnings: provisional, rubric vs AI two grades apart (`GRADE_ORDER`), transcript quality not good; summary | — | `show_result` |
| `show_criteria` | `(assessment)` | one expander per criterion: score or "not assessed", rationale, evidence `± [mm:ss] “quote”: observation` | — | `show_result` |
| `show_points` | `(assessment)` | strengths and improvements side by side, each with timestamp and criterion | — | `show_result` |
| `show_measurements` | `(assessment)` | duration, transcript quality, words/min, teacher talk share, switches/min, teacher questions/min, media minutes, long silences; roles caveat | — | `show_result` |
| `show_trace` | `(assessment)` | AI trace expander: prompt version, served model, effort, tokens, cost, latency, evidence kept | — | `show_result` |

`DATA_NOTICE` — the privacy notice shown above the uploader. `BUSY_NOTICE` — shown while waiting for another session's analysis. `GRADE_ORDER` — Poor … Excellent, from `GRADE_BANDS`.

---

### 5.13 [scripts/](../scripts/) — local-only tools

Never imported by the app. Print aggregates only (no names, no transcript text). Run as `.venv/bin/python -m scripts.<name> "<dataset dir>"`.

**[dataset.py](../scripts/dataset.py)**

| Member | Signature | Does | Called by |
|---|---|---|---|
| `RECORDING_KEY` | regex `B\d{3}\|english\|malayalam` | batch id or language in a file name | `recording_key` |
| `Recording` | dataclass `label, key, transcript_path, video_path` + `name` property (`"excellent/b491"`) | one dataset item | scripts |
| `PreparedRecording` | dataclass `recording, duration_s, transcript, teacher, clean, quality, metrics` | transcript-layer output | scripts |
| `recording_key` | `(path) -> str` | `"B491 Beginner…vtt"` → `"b491"` | `iter_recordings` |
| `iter_recordings` | `(dataset, keys=None)`, yields `Recording` | each `<label>/*.vtt` with its matching `.mp4`, optional key filter | all three scripts |
| `prepare` | `(recording) -> PreparedRecording` | `probe` → `TranscriptParser.parse` → `TranscriptAnalyzer` (teacher, quality) → `Pseudonymiser.apply` → `InteractionAnalyzer.compute` | all three scripts |

**[inspect_transcripts.py](../scripts/inspect_transcripts.py)** — `main(dataset)` prints `HEADER` (column titles), then one row per recording via `row(prepared)` (quality, coverage, wpm, ambiguity, every metric, count of `N` codes found with `SPOKEN_NAME_CODE` = `\bN\d+\b`, `guard_status`), then a count of dictionary words (from `DICTIONARY` = `/usr/share/dict/words`) treated as names. `guard_status(prepared)` runs `NameGuard.check` on the whole pseudonymised transcript → `ok` / `LEAK`.

**[try_judge.py](../scripts/try_judge.py)** — `main(dataset, dry_run, keys)`: `load_env_file` → for each recording `prepare` → `PromptBuilder().build` → `--dry-run`: print payload size; else `ClaudeJudge().assess` → `summary_line` (grade, C1–C7 scores, evidence accepted/checked, transcript quality, tokens, cost, latency) and the full JSON to `eval/runs/<timestamp>/` (git-ignored).

**[try_asr.py](../scripts/try_asr.py)** — `main(dataset, keys)`: for each recording with a video: `probe` (minutes) → `Transcriber().transcribe` (timed) → `words()` of the Whisper and the Zoom VTT transcripts (`WORD` = `[\w']+`, lowercased) → one row: minutes, seconds, times real time, word counts, `word_recall` (share of VTT words, with repeats, also in the Whisper output), `peak_memory_mb`. No text is printed.

**[try_roles.py](../scripts/try_roles.py)** — `main(dataset, keys, names_only)`: for each recording with a video: `Transcriber().transcribe` → `Pseudonymiser(Unknown).apply` → `leaked_lines` (lines still matching any name in the local `redact_names.txt`; stricter than `NameGuard`, which only knows the names found). Any leak, or `--names-only` → print line/name counts and stop, **no Claude call**. Otherwise `RoleLabeller.label` → per line `reference_role` (Zoom cue with the most time overlap: media / teacher / student; Unknown skipped) vs `predicted_role` → accuracy, per-role recall, talk share / turn switches / teacher questions vs the Zoom-labelled metrics, and the call's tokens, cost and latency. Prints aggregates only.

**[evaluate.py](../scripts/evaluate.py)** — `main(dataset, keys, cache)`: `AssessmentPipeline(CachedTranscriber(cache), …, known_names=redact list)` on every recording → per recording: expected grade (`LABEL_TO_GRADE`: excellent/good/average as is, weak and quality issue → Poor; demos none), computed grade, score, assessed share, the AI's overall view, transcript quality → exact and within-one-grade matches and a `confusion` matrix for both the rubric grade and the AI's view, plus the run's Claude cost. `CachedTranscriber` keeps Whisper output in a local folder keyed by `run_id` (`--cache DIR`, never committed). Prints grades and aggregates only.

**[build_redact_list.py](../scripts/build_redact_list.py)** — `main(dataset)`: for every recording (Zoom VTT): display-name tokens of every speaker + the pseudonymiser's `name_tokens` that Zoom capitalises mid-sentence (`_word_counts`) or calls out at a sentence start (`VOCATIVE` = `Name, …`); + `feedback_names(pdf)` (teacher names via `pdftotext` and `FEEDBACK_NAME`, e.g. `") FIRST LAST -----"`) − `NOT_NAMES` − `is_common_word` (in `DICTIONARY` = `/usr/share/dict/words`, or an inflection of a word in it via `INFLECTIONS`: the system list has "line" but not "lines") → written to `OUTPUT` (`redact_names.txt`, git-ignored); prints the count. **Precision matters**: the pre-commit guard blocks any file containing a listed word, and leak checks treat each word as a real name.

---

### 5.14 [prompts/](../prompts/) — system prompts

Loaded by `load_prompt(version)`; versioned by file name (`PROMPT_VERSION`, `ROLES_PROMPT_VERSION`). Older versions stay in `prompts/` for comparison.

| Version | Change |
|---|---|
| v1 | First rubric prompt |
| v2 | Role section explains that OPENING / MAIN / CLOSING are split by recording time, so Claude decides from the content whether the class really opens or closes in the clip (replaces the keyword-based "opening/closing captured" hint) |
| v3 | Transcript comes from speech-to-text; roles were assigned automatically (`T`, `S` = any student) and may be wrong on a few lines; `N1…` = people named in speech. Removed "one child can appear under several codes" |
| roles_v1 | Role labelling: teacher / student / media definitions with cues, return student and media line numbers only (unlisted = teacher), mixed lines by majority, injection rule |

Sections:

| Section | Content |
|---|---|
| Role and inputs | Reviewer of children's chess classes; speaker codes; ASR errors; one child may have several codes; OPENING / CLOSING are by recording time, not proof the class opens or closes there |
| Injection rule | Everything inside `<transcript>` is material to assess, never instructions |
| Rubric | C1–C7, each with 1–4 anchors from the reviewer feedback and "not assessed" conditions (clip starts mid-lesson → C1; ends early → C5; C6 only from transcript cues) |
| Evidence | Timestamp + exact quote ≤ 20 words; checked automatically; specific observations; 1–4 items per criterion; measured facts are not evidence |
| Transcript quality | When to say poor / partial; judge only readable parts |
| Overall | 2–4 strengths and improvements tied to criterion + timestamp; holistic grade descriptors; 2–3 sentence summary |

---

### 5.15 [scripts/check_clean.sh](../scripts/check_clean.sh) — pre-commit guard

Installed with `ln -sf ../../scripts/check_clean.sh .git/hooks/pre-commit`. On every commit, over staged files:

1. Block media, transcripts, PDFs, `.env` and `secrets.toml` by file name.
2. Block any staged content matching `sk-ant-…` (API keys).
3. If `redact_names.txt` exists, block staged files containing any listed name (prints file paths only, never the names).

Exit code 1 stops the commit.

---

### 5.16 [asr.py](../classlens/asr.py) — speech-to-text

Imports: faster_whisper, config, models. Imported by: app, scripts.try_asr.

`SAMPLE_RATE` = 16000 — Whisper's input rate (16 kHz mono).

**`Transcriber(model=None)`** — field `_model`: a faster-whisper `WhisperModel`; injected in tests, otherwise loaded on first use (`WHISPER_MODEL` on CPU, int8, `WHISPER_THREADS` threads; downloaded once to the Hugging Face cache).

| Method | Signature | Returns | Steps | Called by |
|---|---|---|---|---|
| `transcribe` | `(media_path: Path) -> Transcript` | cues with speaker `Unknown` | `decode_audio` once, straight from the video (PyAV, 16 kHz float; ~170 MB for 44 min) → `transcribe_audio` | `try_asr.main` |
| `transcribe_audio` | `(audio) -> Transcript` | same | one `_transcribe_window` per `WHISPER_WINDOW_S` slice, in order. Windows because Whisper builds its input features for everything it gets at once: a whole 44-min class in one call peaked at 2.2 GB | `transcribe`, tests |
| `_transcribe_window` | `(audio, start_s) -> list[Cue]` | cues | `model.transcribe(audio, beam_size=WHISPER_BEAM_SIZE, vad_filter=True)` (VAD skips long silences) → one `Cue` per non-empty segment, times shifted by `start_s` | `transcribe_audio` |
| `_get_model` | `() -> WhisperModel` | the model | load once, keep | `transcribe` |

Whisper gives no speakers; `RoleLabeller` (§5.17) labels lines `T` / `S` / media after pseudonymisation.

---

### 5.17 [llm/roles.py](../classlens/llm/roles.py) — teacher / student / media per line

Imports: config, llm.claude, llm.schema, models, privacy, runlog, timecode. Imported by: scripts.try_roles (phase 4: pipeline).

**`RoleLabeller(client=None, log=None)`** — `_call = StructuredCall("roles", ROLES_PROMPT_VERSION, ROLES_EFFORT, …)`.

| Method | Signature | Returns / raises | Steps | Called by |
|---|---|---|---|---|
| `label` | `(clean: PseudonymisedTranscript) -> PseudonymisedTranscript` | same cues with speaker `T` or `S` and `media` set · `PrivacyError` (nothing sent) · `AIUnavailable` | 1 `_numbered_lines` · 2 **`NameGuard(clean.name_tokens).check`** · 3 `_call.run("<transcript>…</transcript>", RoleLabels)` · 4 line in `media_lines` → media (speaker `T`); in `student_lines` → `S`; else `T`; numbers that don't exist are ignored · 5 log `("roles", "ok", stats + line counts)` | `try_roles.main` |
| `_numbered_lines` | `(cues) -> str` | `"12 [03:41] N1, your move?"` per line, numbered from 1 | — | `label` |

Measured against Zoom speaker labels with `scripts/try_roles.py` (HLD §9.6).

---

### 5.18 [scoring.py](../classlens/scoring.py) — the final grade

Imports: config, llm.schema, models. Imported by: pipeline.

**`Scorer`** (no state)

| Method | Signature | Returns | Steps | Called by |
|---|---|---|---|---|
| `grade` | `(judgement: Judgement) -> GradeResult` | grade, score, assessed weight, provisional | for each assessed criterion with a score: `weighted += weight × (score − 1) / 3`, `assessed_weight += weight` (weights from `CRITERIA`) · nothing assessed → Poor, 0, provisional · `score = 100 × weighted ÷ assessed_weight` (unassessed criteria don't count against the teacher) · `provisional` if assessed weight < `PROVISIONAL_MIN_WEIGHT` of the total · `_band(score)` | `AssessmentPipeline.run` |
| `_band` | `(score) -> str` | grade | first `GRADE_BANDS` entry whose minimum the score reaches | `grade` |

Version 1 uses Claude's criterion scores only; the metric blends of HLD §6.1 (e.g. C2 = 0.5 LLM + 0.5 metrics) and the video/audio gates of §6.3 join once their cut-points are calibrated.

---

### 5.19 [pipeline.py](../classlens/pipeline.py) — one recording → one assessment

Imports: ingest, llm.claude, llm.judge, llm.prompt, llm.roles, metrics, models, privacy, scoring, transcript. Imported by: app, scripts.evaluate.

| Name | Kind | Meaning |
|---|---|---|
| `NO_AUDIO`, `NO_SPEECH` | const | user-facing notes when nothing can be assessed |
| `Assessment` | frozen dataclass | `media`, `quality`, `metrics`, `judge` (`JudgeResult`), `grade` (`GradeResult`), `note`: everything the report shows; `grade` None → `note` says why |

**`AssessmentPipeline(transcriber, labeller=None, judge=None, known_names=frozenset())`** — collaborators injected (tests: fakes; evaluation: cached transcriber). `known_names`: casefolded names always replaced (evaluation passes the local real-name list).

| Method | Signature | Returns | Steps | Called by |
|---|---|---|---|---|
| `run` | `(video_path, facts: dict, on_step) -> Assessment` | Assessment | 1 `probe` (no audio → note) · 2 `transcriber.transcribe` (timed; no cues → note) · 3 `TranscriptAnalyzer.quality` · 4 `Pseudonymiser(Unknown, known_names).apply` · 5 `RoleLabeller.label` · 6 `InteractionAnalyzer.compute` · 7 `PromptBuilder.build` → `ClaudeJudge.assess` · `AIUnavailable` / `PrivacyError` → Assessment with quality and the error as note · 8 `Scorer.grade`. Adds `video_min`, `has_audio`, `transcription_s`, `lines`, `words`, `grade`, `score`, `holistic_grade` (or `ai_skipped`) to `facts`; `on_step(text)` before each slow step | `app.analyse`, `evaluate.main` |

```mermaid
flowchart LR
  run --> probe & Transcriber.transcribe & TranscriptAnalyzer.quality & Pseudonymiser.apply & RoleLabeller.label & InteractionAnalyzer.compute & PromptBuilder.build & ClaudeJudge.assess & Scorer.grade
```

---

## 6. System call graph

Every cross-module call in the built code.

```mermaid
flowchart TB
  subgraph UI[app.py]
    main --> access_granted & upload_widget & run_analysis & show_result
    run_analysis --> analyse
  end
  subgraph ING[ingest.py]
    save_upload
    probe
  end
  analyse --> save_upload & probe

  subgraph DS[scripts/dataset.py]
    prepare
  end
  prepare --> probe
  prepare --> TP_parse[TranscriptParser.parse]
  prepare --> TA_teacher[TranscriptAnalyzer.teacher] & TA_quality[.quality]
  prepare --> PS_apply[Pseudonymiser.apply]
  prepare --> IA_compute[InteractionAnalyzer.compute]

  subgraph LLM[llm/]
    PB_build[PromptBuilder.build]
    CJ_assess[ClaudeJudge.assess]
    EV_validate[EvidenceValidator.validate]
  end
  TJ[try_judge.main] --> prepare & PB_build & CJ_assess
  PB_build --> NG_check[NameGuard.check]
  PB_build --> format_time
  CJ_assess --> EV_validate
  EV_validate --> parse_time
  CJ_assess --> LOG[RunLog.record]
  CJ_assess --> COST[estimate_cost]
  CJ_assess --> API[(Claude API)]
  IR[inspect_transcripts.main] --> prepare & NG_check
  BR[build_redact_list.main] --> prepare & DNT[display_name_tokens]
```

---

## 7. Errors

| Exception | Defined in | Raised by | Meaning | Handled by |
|---|---|---|---|---|
| `IngestError` | ingest.py | `probe`, `_run_ffprobe` | unreadable file, zero length, no video stream | `app.run_analysis` shows the message |
| `PrivacyError` | privacy.py | `NameGuard.check` (via `PromptBuilder.build`, `RoleLabeller.label`) | a real name would leave the server | phase 4 pipeline: skip AI step, local-only, flag it |
| `AIUnavailable` | llm/claude.py | `StructuredCall.run` for `ClaudeJudge` and `RoleLabeller` (no key, 401, 429, other API error, connection, refusal, unreadable twice) | AI step can't run | `try_judge.main` prints it; phase 4 pipeline: local-only + banner |
| `ValueError` | built-in | `InteractionAnalyzer.__init__` | no attributed speech | phase 4 pipeline: transcript criteria not assessed |

Every user-facing message is written in the exception itself; no stack traces reach the UI.

---

## 8. Tests

`.venv/bin/python -m pytest` — 82 tests, synthetic data only, no network.

| Test file | Module | Tests | Covers |
|---|---|---|---|
| test_config.py | config | 2 | `.env` parsing, precedence, missing file |
| test_models.py | models | 2 | `Transcript` helpers, `QualityLevel` text |
| test_timecode.py | timecode | 2 | format / parse incl. hours and ranges |
| test_ingest.py | ingest | 6 | probe on generated media (video+audio, silent video, audio-only rejected, corrupt), generic upload name, run id from content not name |
| test_transcript.py | transcript | 10 | Zoom VTT, SRT + BOM, voice tags/settings/missing labels, clock-time false speaker, sorting, teacher rules, quality levels |
| test_privacy.py | privacy | 16 | display-name tokens, speaker codes, names in text, N codes, common words, lowercase rule, sentence-start names, mid-sentence names in unlabelled speech-to-text, a name alone at line start, contact details, media/unknown, no teacher, `NameGuard` |
| test_metrics.py | metrics | 3 | all 7 metrics on a hand-counted class, speech-to-text `S` code, no speech |
| test_prompt.py | llm.prompt | 6 | merging, long-turn split, sections and phases, empty findings, name guard on transcript and on findings |
| test_evidence.py | llm.evidence | 4 | grounded vs wrong-time vs invented quotes, completion and duplicate criteria, points, media lines |
| test_judge.py | llm.claude, llm.judge | 12 | request shape, retry, refusal, unreadable, 401/429/500/connection, missing key, log has no transcript text, refusal logged, versioned system prompt |
| test_roles.py | llm.roles | 3 | unlisted lines = teacher, student/media mapping, out-of-range numbers ignored, request text and prompt, name guard blocks the call |
| test_runlog.py | runlog | 4 | cost per token kind, missing cache fields, JSON lines written and printed, peak memory |
| test_scoring.py | scoring | 8 | uniform scores per level, bands between levels, unassessed criteria ignored, provisional, nothing assessed |
| test_pipeline.py | pipeline | 3 | full run on a generated video with fake transcriber + fake Claude (grade, facts, names replaced before any call), no audio, no speech, AI failure keeps quality |
| test_asr.py | asr | 1 | fake Whisper model: 25 s in 10 s windows → 3 calls, times shifted per window, empty segments dropped, VAD on |

Helpers: [tests/fakes.py](../tests/fakes.py) — sample cues, metrics, `judgement()`, `response()`, `FakeClient` (stands in for `anthropic.Anthropic`).

---

## 9. Planned components (phases 3–5)

Interfaces to implement; they follow the same conventions.

| Module › class | Public method | Returns | Notes |
|---|---|---|---|
| audio.py › `AudioAnalyzer(media_path)` | `speech_activity() -> list[float]` | per-second RMS | `ffmpeg` → 16 kHz mono PCM → NumPy |
| | `teacher_features(intervals) -> AudioFeatures` | loudness variation, pitch variability, speech rate, dropouts, dead air | intervals = teacher cue times |
| video.py › `VideoAnalyzer(media_path, logo_path)` | `analyse(sample_times) -> VideoFindings` | camera-off %, face-visible %, low-light %, branded background %, screen-share %, freezes, blur | frames stay in memory; OpenCV |
| | `VideoFindings.facts() -> list[str]` | sentences for `PromptBuilder(findings)` | must pass `NameGuard` |
| scoring.py › `Scorer` (v2) | metric blends per criterion and video/audio gates (HLD §6.1, §6.3), confidence | | once cut-points are calibrated |
| report.py › `ReportRenderer` | `to_markdown(report)`, `to_json(report)` | str | UI view and download |

---

## 10. Coding conventions

1. **One job per function**, ≤ ~25 lines; a public method reads as a list of named steps.
2. **Plain over clever**: explicit loops when a step both filters and transforms; no walrus operators, no `zip([None, *x], x)`, no conditional list-splatting.
3. **Every regex is a named module constant** with a comment showing what it matches.
4. **Data vs behaviour**: data types in `models.py` (or next to their only user, e.g. `CallStats`, `JudgeResult`); classes for multi-step processes; module functions for small pure helpers.
5. **Enums, not magic strings**, for fixed sets (`QualityLevel`).
6. **No thresholds in logic**: every number lives in `config.py` or is a named constant with a reason.
7. **Type hints wherever a built-in type can say it** (`list[Cue]`, `dict[str, int]`, `float | None`); a docstring on every public class and on non-obvious methods.
8. **No duplication**: shared logic lives once (`Transcript.speech()`, `timecode`, `names_pattern`, `scripts/dataset.py`).
9. **Tests** use synthetic data, exercise public methods, and mirror module names (`test_<module>.py`).
10. **Every import earns its place.** No import for something a built-in does in the same amount of code (`dict` + `.get()` not `Counter`, `vars()` not `asdict`, calling `Cue(...)` not `dataclasses.replace`), and no import used only for a type hint (say the type in the docstring). Kept because the plain version would be longer or riskier: `dataclass` (writes `__init__`/`__repr__`/`__eq__`; `frozen` stops one step changing data another step reads), `enum`, `difflib` (fuzzy quote match), `hmac.compare_digest` (constant-time access-code check), `typing.Literal` (becomes the allowed values in Claude's answer schema). New third-party packages only with the user's approval.

---

## 11. Change log

### v2 — 2026-10-22: refactor to classes, detailed LLD

| Before (v1 code) | After |
|---|---|
| `transcript.parse()` with walrus operators | `TranscriptParser.parse()` + 5 named steps |
| `detect_teacher()`, `assess_quality()`, `detect_boundaries()` | `TranscriptAnalyzer.teacher()`, `.quality()`, `.boundaries()` |
| `privacy.pseudonymise()` — ~40 lines with a nested closure | `Pseudonymiser.apply()` + 5 private steps |
| `privacy.name_tokens()`, `check_no_names()` | `display_name_tokens()`, `NameGuard.check()` |
| `metrics.compute()` — ~40 lines of comprehensions | `InteractionAnalyzer.compute()` + one method per metric |
| `judge.py` — 240 lines mixing schema, payload, API call, validation | `llm/schema.py`, `llm/prompt.py`, `llm/evidence.py`, `llm/judge.py` |
| `meta` dict mutated in `call_claude` | `CallStats` dataclass |
| `"A"`–`"E"`, `"good"/"partial"/"poor"` strings; `MODES` dict | `InputMode`, `QualityLevel` enums |
| `format_time` / `parse_time` inside judge.py | `timecode.py` |
| `ailog.log_call()`, `cost_usd()` | `AICallLog.record()`, `estimate_cost()` |
| `recording_key()` copied into two scripts; pipeline steps repeated | `scripts/dataset.py`: `iter_recordings()`, `prepare()` |
| `app.py` flow as top-level statements | `main()` + `upload_widgets()`, `run_analysis()` |

### v2.1 — 2026-10-22: fewer imports

Removed `typing.BinaryIO`, `collections.abc.Iterator` (hint-only), `collections.Counter` (→ `dict`), `dataclasses.replace` (→ `Cue(...)`), `dataclasses.asdict` (→ `vars()`). Convention 10 added. Tests: 77 passing.

### v2.2 — 2026-10-22: no keyword guessing of meaning

Removed `OPENING_MARKERS`, `CLOSING_MARKERS`, `TranscriptAnalyzer.boundaries`, `ClipBoundaries`, `BOUNDARY_WINDOW_MIN` and the "Opening/closing captured" payload line; removed `GREETING`, `PRAISE`, `praise_per_min`, `opening_greetings` and the unused `students_addressed_share`. Claude now judges greetings, praise and whether the clip includes the class opening/closing from the transcript itself (prompt v2). Counting metrics, parsing and name removal stay in code. Tests: 77 → 75 (the two boundary tests went with the feature).

### v2.3 — 2026-10-22: video is the only input

The brief promises only the recording. Removed the transcript uploader, `TRANSCRIPT_EXTENSIONS`, audio-only uploads, `ingest.choose_mode`, `InputMode` and `MediaInfo.has_video` (`probe` now rejects files without video). `upload_widgets` → `upload_widget`; a video without audio shows `NO_AUDIO_NOTICE`. `TranscriptParser` stays for the offline scripts that read the labelled set's Zoom VTTs. Tests: 75 → 66.

### v2.4 — 2026-10-22: local speech-to-text

Added `asr.py` › `Transcriber` (faster-whisper 1.2.1, base, int8, 2 threads, greedy, 10-min windows), `WHISPER_*` settings, `scripts/try_asr.py` and `test_asr.py`. Removed the planned VTT–audio `Aligner` (no uploaded VTT to align). Tests: 66 → 67.

### v2.5 — 2026-10-22: speaker roles without Zoom labels

Added `llm/claude.py` (`StructuredCall`, `CallStats`, `AIUnavailable`, `load_prompt`: the Claude call shared by both AI steps; replaces `ClaudeJudge`'s private retry/client/error code and `JudgeUnavailable`), `llm/roles.py` › `RoleLabeller` + `RoleLabels` schema + `prompts/roles_v1.md`, `STUDENT_CODE`, `privacy.CAPITALISED_WORD` (any capitalised word never seen in lowercase is a name; replaces the greeting and mid-sentence patterns after a line-start name slipped through on real data) + more `NOT_NAMES`, prompt `judge_v3`, `scripts/try_roles.py`. Removed per-student metrics (`students_present`, `participation_gini`, `one_to_one`, `gini`): speech-to-text can't tell students apart. Tests: 67 → 67 (7 removed with per-student metrics and the old prompt loader, 7 added).

### v2.6 — 2026-10-22: run log

`ailog.py` › `AICallLog` → `runlog.py` › `RunLog` (`AI_LOG_PATH` → `RUN_LOG_PATH`, `logs/runs.jsonl`); each line is also printed for the Cloud log view. `app.run_analysis` writes one `analysis` line per run (outcome, wait, timings, counts, peak memory); `ingest.run_id` (SHA-256 of the first 1 MiB) identifies runs without file names; `peak_memory_mb` moved from `try_asr` to `runlog`. Tests: 67 → 69.

### v2.7 — 2026-10-22: four-grade classification end to end

Added `scoring.py` › `Scorer` (criterion scores → 0–100 → `GRADE_BANDS`), `models.GradeResult`, `pipeline.py` › `AssessmentPipeline` + `Assessment`, `Pseudonymiser(known_names=…)`, the report page in `app.py` (`show_grade`, `show_criteria`, `show_points`, `show_measurements`, `show_trace`; progress via `st.status`), `scripts/evaluate.py`. Removed `app.transcriber` (now `app.pipeline`). Tests: 70 → 82.

### v2 verification

**Behaviour verified unchanged:** before the refactor, a script fingerprinted (SHA-256) nine outputs for each of the 12 recordings — parsed cues, teacher guess, pseudonymised cues, name tokens, quality, boundaries, metrics, payload text, payload lines. After the refactor the same fingerprints were recomputed with the new classes: **0 differences**. Tests: 54 → 77, all passing.
