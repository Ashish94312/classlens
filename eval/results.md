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

## Run 2 — 2026-10-23: with video checks

Same setup as run 1, plus the video checks (HLD §5 step 6): 120 moments at the middle of the teacher's lines (as labelled by Claude from the Whisper text), checked on the laptop with OpenCV; findings go into the prompt; C6 = the lower of the video score and Claude's; C7 = mean of the two; gates: camera off > 30%, face visible < 30% (one flag caps at Average). Same Whisper transcripts as the app would make (cached for this run). Claude cost for 12 recordings: $2.05. Wall time 73 min for 12 classes, almost all of it Whisper; video checks ~15 s per class on the laptop.

| Recording | Label | Expected | Run 1 rubric grade | Run 2 rubric grade (score) | Claude's overall view | Camera off | Face visible | Dark face | Gate flags |
|---|---|---|---|---|---|---|---|---|---|
| B435 | average | Average | Poor (38.9) | Poor (37.5) | Average | 3% | 40% | 68% | 0 |
| B516 | average | Average | **Average** (48.3) | **Average** (50.0) | Average | 10% | 98% | 1% | 0 |
| English demo | demo | — | Average (57.4) | Average (57.5) | Average | 0% | 100% | 1% | 0 |
| Malayalam demo | demo | — | Average (53.8) | Average (58.3) | Average | 6% | 100% | 2% | 0 |
| B472 | excellent | Excellent | Good (64.8) | Good (75.0) | Good | 2% | 94% | 1% | 0 |
| B491 | excellent | Excellent | Good (68.3) | Good (69.2) | Good | 9% | 94% | 2% | 0 |
| B435 | good | Good | Poor (37.0) | Poor (45.0) | Average | 19% | 98% | 1% | 0 |
| B552 | good | Good | **Good** (66.7) | **Good** (65.0) | Good | 0% | 83% | 0% | 0 |
| B392 | quality issue | Poor | Average (51.9) | Good (64.2) | Average | 11% | 90% | 1% | 0 |
| B441 | quality issue | Poor | Average (59.3) | Average (49.2) | Average | 10% | **4%** | 0% | **1** (face) |
| B482 | weak | Poor | **Poor** (43.3) | **Poor** (43.3) | Average | 5% | 99% | 4% | 0 |
| B558 | weak | Poor | Average (51.9) | Average (53.3) | Average | 9% | 94% | 0% | 0 |

| | Exact | Within one grade |
|---|---|---|
| Rubric grade, run 1 | 3/10 | 9/10 |
| Rubric grade, run 2 | 3/10 | 8/10 |
| Claude's overall view, run 2 | 3/10 | 10/10 |

What it shows:

1. The video checks find the visual problems the reviewers wrote down: B441 ("face not visible") shows the teacher's face in 4% of camera-on moments and raises the face gate; its score falls from 59.3 to 49.2, 1.2 points above Poor. B435 (average) is flagged for a dark face (68% of face moments).
2. Accuracy did not move. Two reasons: one gate flag caps at Average, which B441 already was; and Claude's criterion scores vary between runs by more than the video changes them. B392 went from 51.9 to 64.2, of which the video can explain about 3 points (C6 = 3 now counted at weight 10; the video's C7 = 4 lifts the C7 blend); the rest is run-to-run variance in C1–C5. B472 moved +10 the same way.
3. B392's reviewer problem (no branded background, repeated quality complaints) is still not measured: the background check needs a logo template, and its camera, face and light look normal.
4. Next levers, in order: run-to-run stability of the judge (e.g. score twice and average, or a stricter prompt); the background gate (needs `assets/brand_logo.png`); whether a severe face/camera problem should cap at Poor.
