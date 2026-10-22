# Evaluation results

Produced by `scripts/evaluate.py` on the 12 sample recordings (local only). Grades and aggregates only; recordings are referred to by batch id.

## Run 1 — 2026-10-22: transcript only (no video or audio checks yet)

Setup: video → faster-whisper base (int8, greedy, 10-min windows) → pseudonymised → roles by Claude Opus 5.5 (`roles_v1`, low effort) → metrics → rubric judgement by Claude Opus 5.5 (`judge_v3`, medium effort) → `Scorer` with the initial bands (Excellent ≥ 78 · Good ≥ 62 · Average ≥ 48 · Poor). Label mapping: weak and known-quality-issue → Poor. Claude cost for 12 recordings: $2.00.

| Recording | Label | Expected | Rubric grade (score, share assessed) | Claude's overall view | Transcript quality (Claude) |
|---|---|---|---|---|---|
| B435 | average | Average | Poor (38.9, 90%) | Average | good |
| B516 | average | Average | **Average** (48.3, 100%) | Average | partial |
| English demo | demo | — | Average (57.4, 90%) | Average | partial |
| Malayalam demo | demo | — | Average (53.8, 65%) | Average | poor |
| B472 | excellent | Excellent | Good (64.8, 90%) | Average | partial |
| B491 | excellent | Excellent | Good (68.3, 100%) | Good | good |
| B435 | good | Good | Poor (37.0, 90%) | Average | partial |
| B552 | good | Good | **Good** (66.7, 100%) | Good | partial |
| B392 | quality issue | Poor | Average (51.9, 90%) | Average | partial |
| B441 | quality issue | Poor | Average (59.3, 90%) | Average | partial |
| B482 | weak | Poor | **Poor** (43.3, 100%) | Average | partial |
| B558 | weak | Poor | Average (51.9, 90%) | Average | partial |

| | Exact | Within one grade |
|---|---|---|
| Rubric grade | 3/10 | 9/10 |
| Claude's overall view | 3/10 | 9/10 |

Rubric grade (rows: expected, columns: computed):

| | Poor | Average | Good | Excellent |
|---|---|---|---|---|
| Poor | 1 | 3 | 0 | 0 |
| Average | 1 | 1 | 0 | 0 |
| Good | 1 | 0 | 1 | 0 |
| Excellent | 0 | 0 | 2 | 0 |

What it shows:

1. Both excellent classes and one good class score highest (64.8–68.3), but scores are compressed: Claude rarely gives 4/4, so the Excellent band (78) is never reached.
2. Transcript-only scores do not separate Average from Poor. Both known-quality-issue classes land in Average (51.9, 59.3): their problems are on screen and in the connection (camera, background, freezes), which the transcript cannot show. The video and audio checks and gates (HLD §6.3) are meant for exactly this.
3. One good class (B435) scores 37.0, an outlier to examine per criterion.
