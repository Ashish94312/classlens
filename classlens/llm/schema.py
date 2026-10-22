"""Shape of Claude's answers. The Anthropic SDK turns RoleLabels and Judgement into the JSON
schema Claude must follow, and parses the answer back into these objects."""

from typing import Literal

from pydantic import BaseModel

CriterionId = Literal["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
Grade = Literal["Poor", "Average", "Good", "Excellent"]


class RoleLabels(BaseModel):
    """Who speaks each numbered transcript line. Lines in neither list are the teacher's."""

    student_lines: list[int]  # spoken by a child (or a parent speaking for one)
    media_lines: list[int]  # recorded audio playing, e.g. a chess video the teacher shares


class Evidence(BaseModel):
    timestamp: str  # "mm:ss" or "h:mm:ss", as shown in the transcript
    quote: str  # short exact quote from that line
    observation: str  # what it shows, specifically
    polarity: Literal["positive", "negative"]


class CriterionAssessment(BaseModel):
    criterion_id: CriterionId
    assessed: bool  # false when the input can't show this criterion
    score: Literal[1, 2, 3, 4] | None  # None when not assessed
    rationale: str  # reasoning, or why it could not be assessed
    evidence: list[Evidence]


class Point(BaseModel):
    """A strength or an improvement, tied to a criterion and a moment in the class."""

    criterion_id: CriterionId
    timestamp: str
    text: str


class Judgement(BaseModel):
    criteria: list[CriterionAssessment]
    strengths: list[Point]
    improvements: list[Point]
    holistic_grade: Grade
    transcript_quality: Literal["good", "partial", "poor"]
    summary: str
