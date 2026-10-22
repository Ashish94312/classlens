"""Builds the payload: the only text that leaves the server (HLD §8.2, LLD §5.8)."""

from classlens import config
from classlens.models import (
    Cue,
    InteractionMetrics,
    Payload,
    PseudonymisedTranscript,
    Transcript,
    TranscriptQuality,
)
from classlens.privacy import NameGuard
from classlens.timecode import format_time


def merge_lines(transcript: Transcript) -> list[Cue]:
    """Consecutive cues by the same speaker become one line (up to MAX_BLOCK_S long); a run of
    shared-media cues becomes one line however long it is."""
    lines: list[Cue] = []
    for cue in transcript.cues:
        previous = lines[-1] if lines else None
        same_source = (
            previous is not None and previous.speaker == cue.speaker and previous.media == cue.media
        )
        fits = cue.media or (previous is not None and cue.end - previous.start <= config.MAX_BLOCK_S)
        if same_source and fits:
            text = f"{previous.text} {cue.text}"
            lines[-1] = Cue(previous.start, cue.end, previous.speaker, text, previous.media)
        else:
            lines.append(cue)
    return lines


class PromptBuilder:
    """Assembles facts, metrics and the de-identified transcript into one Payload."""

    def __init__(self, findings: list[str] | None = None):
        self.findings = findings or []  # video/audio facts as sentences (phase 3)

    def build(
        self,
        clean: PseudonymisedTranscript,
        metrics: InteractionMetrics,
        quality: TranscriptQuality,
        duration_s: float | None,
    ) -> Payload:
        """Raises PrivacyError (nothing is sent) if a real name is still present."""
        lines = merge_lines(clean.transcript)
        transcript_lines = self._transcript_section(lines)
        # Check everything derived from the recording; the template text around it is fixed.
        NameGuard(clean.name_tokens).check("\n".join([*transcript_lines, *self.findings]))

        sections = [
            *self._recording_section(metrics, quality, duration_s),
            "",
            *self._metrics_section(metrics),
            "",
            *self._findings_section(),
            "",
            "<transcript>",
            *transcript_lines,
            "</transcript>",
        ]
        return Payload("\n".join(sections), lines)

    @staticmethod
    def _recording_section(
        metrics: InteractionMetrics,
        quality: TranscriptQuality,
        duration_s: float | None,
    ) -> list[str]:
        minutes = duration_s / 60 if duration_s else metrics.minutes
        return [
            "RECORDING",
            f"- Length: {minutes:.0f} min",
            f"- Transcript quality from text signals: {quality.level} ({quality.words_per_min:.0f} words/min)",
        ]

    @staticmethod
    def _metrics_section(metrics: InteractionMetrics) -> list[str]:
        section = [
            "MEASURED INTERACTION",
            f"- Teacher share of spoken words: {metrics.teacher_talk_share:.0%}",
            f"- Teacher/student turn switches: {metrics.turn_switches_per_min:.1f} per min",
            f"- Teacher questions: {metrics.teacher_questions_per_min:.1f} per min "
            f"({metrics.named_question_share:.0%} name someone)",
        ]
        section.append(
            f"- Shared media played: {metrics.media_minutes:.1f} min; "
            f"silences over {config.LONG_GAP_S} s: {metrics.long_gaps}"
        )
        return section

    def _findings_section(self) -> list[str]:
        section = ["VIDEO AND AUDIO FINDINGS"]
        if not self.findings:
            section.append("- Not analysed for this run.")
        for finding in self.findings:
            section.append(f"- {finding}")
        return section

    @staticmethod
    def _transcript_section(lines: list[Cue]) -> list[str]:
        """Rendered lines with OPENING / MAIN / CLOSING markers, e.g. "[12:31] T: S3, your move?"."""
        start = lines[0].start
        end = max(line.end for line in lines)
        opening_end = start + config.OPENING_WINDOW_MIN * 60
        closing_start = end - config.CLOSING_WINDOW_MIN * 60

        rendered: list[str] = []
        current_phase = None
        for line in lines:
            phase = _phase(line.start, opening_end, closing_start)
            if phase != current_phase:
                rendered.append(f"=== {phase} ===")
                current_phase = phase
            rendered.append(_render(line))
        return rendered


def _phase(start: float, opening_end: float, closing_start: float) -> str:
    if start < opening_end:
        return "OPENING"
    if start >= closing_start:
        return "CLOSING"
    return "MAIN"


def _render(line: Cue) -> str:
    if line.media:
        return f"[{format_time(line.start)}] (shared audio or video playing until {format_time(line.end)})"
    return f"[{format_time(line.start)}] {line.speaker}: {line.text}"
