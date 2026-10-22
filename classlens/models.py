"""Domain data shared across modules (LLD §4). No I/O and no analysis logic."""

from dataclasses import dataclass
from enum import StrEnum

UNKNOWN_SPEAKER = "Unknown"  # speaker of a cue without a label
TEACHER_CODE = "T"  # pseudonymised teacher; other people named in speech are N1, N2…
STUDENT_CODE = "S"  # any student: speech-to-text can't tell students apart (Zoom VTTs give S1, S2…)


@dataclass(frozen=True)
class Cue:
    """One transcript line."""

    start: float  # seconds from the start of the recording
    end: float
    speaker: str
    text: str
    media: bool = False  # computer audio shared by the host (e.g. a video), not speech

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class Transcript:
    """Cues in time order."""

    cues: list[Cue]

    def speech(self) -> list[Cue]:
        """Cues that are people speaking (shared media excluded)."""
        return [cue for cue in self.cues if not cue.media]

    def start(self) -> float:
        return min(cue.start for cue in self.cues)

    def end(self) -> float:
        return max(cue.end for cue in self.cues)


@dataclass(frozen=True)
class PseudonymisedTranscript:
    """Transcript with speakers as T / S1.. / N1.. and real names replaced in the text."""

    transcript: Transcript
    name_tokens: frozenset[str]  # casefolded real-name tokens, kept in memory for NameGuard


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    has_audio: bool
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class TeacherGuess:
    speaker: str
    ambiguous: bool  # the UI asks the user to confirm


class QualityLevel(StrEnum):
    GOOD = "good"
    PARTIAL = "partial"
    POOR = "poor"


@dataclass(frozen=True)
class TranscriptQuality:
    coverage: float | None  # share of the recording spanned by speech; None without a recording
    words_per_min: float
    non_latin_share: float
    level: QualityLevel


@dataclass(frozen=True)
class InteractionMetrics:
    minutes: float
    teacher_talk_share: float  # teacher words / all spoken words (shared media excluded)
    turn_switches_per_min: float  # teacher ↔ student changes of speaker
    teacher_questions_per_min: float
    named_question_share: float  # teacher questions that address someone by name
    media_minutes: float
    long_gaps: int  # silences longer than LONG_GAP_S with no speech


@dataclass(frozen=True)
class GradeResult:
    """The final classification and how it was reached."""

    grade: str  # Poor / Average / Good / Excellent
    score: float  # 0–100, weighted over the assessed criteria
    assessed_weight: float  # share of the total rubric weight that could be assessed
    provisional: bool  # assessed_weight below PROVISIONAL_MIN_WEIGHT


@dataclass(frozen=True)
class Payload:
    """The only text sent to the AI model, plus the transcript lines exactly as shown to it."""

    text: str
    lines: list[Cue]
