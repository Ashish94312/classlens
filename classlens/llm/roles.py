"""Teacher / student / media label for each line of a speech-to-text transcript (HLD §9.1, LLD §5.17).

Whisper gives no speakers, so one low-effort Claude call reads the pseudonymised lines and says
which ones a student spoke and which are recorded media; every other line is the teacher's.
"""

from classlens import config
from classlens.llm.claude import StructuredCall
from classlens.llm.schema import RoleLabels
from classlens.models import STUDENT_CODE, TEACHER_CODE, Cue, PseudonymisedTranscript, Transcript
from classlens.privacy import NameGuard
from classlens.runlog import RunLog
from classlens.timecode import format_time


class RoleLabeller:
    """One structured Claude call over the numbered, pseudonymised lines."""

    def __init__(self, client=None, log: RunLog | None = None):
        self._call = StructuredCall("roles", config.ROLES_PROMPT_VERSION, config.ROLES_EFFORT, client, log)

    def label(self, clean: PseudonymisedTranscript) -> PseudonymisedTranscript:
        """Raises PrivacyError (nothing is sent) if a real name is still present, AIUnavailable if
        Claude gives no usable answer."""
        text = self._numbered_lines(clean.transcript.cues)
        NameGuard(clean.name_tokens).check(text)
        labels, stats = self._call.run(f"<transcript>\n{text}\n</transcript>", RoleLabels)

        students, media = set(labels.student_lines), set(labels.media_lines)
        cues = []
        for number, cue in enumerate(clean.transcript.cues, start=1):
            speaker = STUDENT_CODE if number in students and number not in media else TEACHER_CODE
            cues.append(Cue(cue.start, cue.end, speaker, cue.text, media=number in media))
        self._call.log.record("roles", "ok", {
            **stats.as_dict(),
            "lines": len(cues),
            "student_lines": sum(1 for cue in cues if cue.speaker == STUDENT_CODE),
            "media_lines": sum(1 for cue in cues if cue.media),
        })
        return PseudonymisedTranscript(Transcript(cues), clean.name_tokens)

    @staticmethod
    def _numbered_lines(cues: list[Cue]) -> str:
        """Lines like "12 [03:41] N1, your move?"; numbers start at 1."""
        lines = []
        for number, cue in enumerate(cues, start=1):
            lines.append(f"{number} [{format_time(cue.start)}] {cue.text}")
        return "\n".join(lines)
