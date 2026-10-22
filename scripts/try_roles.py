"""Local-only: check the video-only path against the Zoom VTT of labelled recordings (LLD §5.13).

Whisper → pseudonymise → (no known name left?) → Claude role labels, then per line: does the role match the Zoom speaker
at that time? Also counts real names (from redact_names.txt) left after pseudonymisation.
Prints aggregates only, never names or transcript text. Costs one Claude call per recording.
Usage: .venv/bin/python -m scripts.try_roles "<dataset dir>" [--names-only] [keys...]
  --names-only: stop after the name check (no Claude call, no cost)
"""

import json
import sys
import tempfile
from pathlib import Path

from classlens import config
from classlens.asr import Transcriber
from classlens.llm.roles import RoleLabeller
from classlens.metrics import InteractionAnalyzer
from classlens.models import TEACHER_CODE, UNKNOWN_SPEAKER, Cue, Transcript
from classlens.privacy import Pseudonymiser, names_pattern
from classlens.runlog import RunLog
from classlens.transcript import TranscriptAnalyzer, TranscriptParser
from scripts.dataset import iter_recordings

REDACT_LIST = config.ROOT / "redact_names.txt"
ROLES = ("teacher", "student", "media")


def reference_role(cue: Cue, vtt: Transcript, teacher: str) -> str | None:
    """Role of the Zoom cue that overlaps this line the most; None if no labelled overlap."""
    best, best_overlap = None, 0.0
    for ref in vtt.cues:
        overlap = min(cue.end, ref.end) - max(cue.start, ref.start)
        if overlap > best_overlap:
            best, best_overlap = ref, overlap
    if best is None or best.speaker == UNKNOWN_SPEAKER:
        return None
    if best.media:
        return "media"
    return "teacher" if best.speaker == teacher else "student"


def predicted_role(cue: Cue) -> str:
    if cue.media:
        return "media"
    return "teacher" if cue.speaker == TEACHER_CODE else "student"


def leaked_lines(transcript: Transcript) -> int:
    """Lines that still contain a name from the local redact list (0 if there is no list)."""
    if not REDACT_LIST.exists():
        return 0
    pattern = names_pattern({line.strip().casefold() for line in REDACT_LIST.read_text().splitlines() if line.strip()})
    return sum(1 for cue in transcript.cues if pattern and pattern.search(cue.text))


def main(dataset: Path, keys: set[str], names_only: bool) -> None:
    config.load_env_file()
    transcriber = Transcriber()
    with tempfile.TemporaryDirectory() as tmp:
        log = RunLog(Path(tmp) / "calls.jsonl")
        labeller = RoleLabeller(log=log)
        for recording in iter_recordings(dataset, keys):
            if recording.video_path is None:
                continue
            clean = Pseudonymiser(UNKNOWN_SPEAKER).apply(transcriber.transcribe(recording.video_path))
            leaks = leaked_lines(clean.transcript)
            if leaks or names_only:  # stricter than NameGuard, which only knows the names we found
                print(f"{recording.name}: {len(clean.transcript.cues)} lines, {len(clean.name_tokens)} names replaced, "
                      f"{leaks} lines still hold a known name{'; not sent to Claude' if leaks else ''}")
                continue
            labelled = labeller.label(clean).transcript
            call = json.loads(log.path.read_text().splitlines()[-1])

            vtt = TranscriptParser().parse(recording.transcript_path.read_text(encoding="utf-8", errors="replace"))
            teacher = TranscriptAnalyzer(vtt).teacher().speaker
            pairs = [(reference_role(cue, vtt, teacher), predicted_role(cue)) for cue in labelled.cues]
            pairs = [(ref, pred) for ref, pred in pairs if ref is not None]
            accuracy = sum(ref == pred for ref, pred in pairs) / max(len(pairs), 1)
            recalls = []
            for role in ROLES:
                of_role = [pred for ref, pred in pairs if ref == role]
                hits = sum(pred == role for pred in of_role)
                recalls.append(f"{role} {hits}/{len(of_role)}")

            vtt_metrics = InteractionAnalyzer(Pseudonymiser(teacher).apply(vtt).transcript).compute()
            asr_metrics = InteractionAnalyzer(labelled).compute()
            print(
                f"{recording.name}: {len(labelled.cues)} lines, {len(clean.name_tokens)} names replaced, "
                f"no known name left\n"
                f"  role accuracy {accuracy:.0%} on {len(pairs)} lines; recall: {', '.join(recalls)}\n"
                f"  teacher talk share {asr_metrics.teacher_talk_share:.0%} (Zoom {vtt_metrics.teacher_talk_share:.0%}); "
                f"turn switches/min {asr_metrics.turn_switches_per_min:.1f} (Zoom {vtt_metrics.turn_switches_per_min:.1f}); "
                f"teacher questions/min {asr_metrics.teacher_questions_per_min:.1f} (Zoom {vtt_metrics.teacher_questions_per_min:.1f})\n"
                f"  Claude: {call['input_tokens']} in / {call['output_tokens']} out tokens, "
                f"${call['cost_usd']:.3f}, {call['latency_s']:.0f} s"
            )


if __name__ == "__main__":
    args = sys.argv[2:]
    main(Path(sys.argv[1]), {key.lower() for key in args if key != "--names-only"}, "--names-only" in args)
