"""Keeps only evidence Claude can back up with the transcript (HLD §7.5, LLD §5.9)."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from classlens import config
from classlens.llm.schema import CriterionAssessment, Evidence, Judgement, Point
from classlens.models import Cue
from classlens.timecode import parse_time

# Punctuation and symbols, removed before comparing quotes: "Very good!" ~ "very good"
NON_WORD = re.compile(r"[^\w\s]")
MIN_MATCH_RUN = 4  # shorter matching runs are coincidences (single letters, "the ")


@dataclass(frozen=True)
class ValidationResult:
    judgement: Judgement  # with ungrounded evidence and points removed, all criteria present
    counts: dict[str, tuple[int, int]]  # criterion id → (accepted, rejected) evidence


class EvidenceValidator:
    """Checks each cited quote against the transcript lines that were shown to Claude."""

    def __init__(self, lines: list[Cue]):
        self.lines = lines

    def validate(self, judgement: Judgement) -> ValidationResult:
        criteria: dict[str, CriterionAssessment] = {}
        counts: dict[str, tuple[int, int]] = {}
        for item in judgement.criteria:
            if item.criterion_id in criteria:
                continue  # first answer for a criterion wins
            criteria[item.criterion_id], counts[item.criterion_id] = self._check_criterion(item)
        self._add_missing(criteria, counts)

        checked = judgement.model_copy(update={
            "criteria": [criteria[criterion_id] for criterion_id in config.CRITERIA],
            "strengths": self._grounded_points(judgement.strengths),
            "improvements": self._grounded_points(judgement.improvements),
        })
        return ValidationResult(checked, counts)

    def _check_criterion(self, item: CriterionAssessment) -> tuple[CriterionAssessment, tuple[int, int]]:
        kept = [evidence for evidence in item.evidence if self._is_grounded(evidence)]
        assessed = item.assessed and item.score is not None
        checked = item.model_copy(update={
            "evidence": kept,
            "assessed": assessed,
            "score": item.score if assessed else None,
        })
        return checked, (len(kept), len(item.evidence) - len(kept))

    @staticmethod
    def _add_missing(criteria: dict[str, CriterionAssessment], counts: dict[str, tuple[int, int]]) -> None:
        """Criteria Claude didn't return are 'not assessed'."""
        for criterion_id in config.CRITERIA:
            counts.setdefault(criterion_id, (0, 0))
            if criterion_id not in criteria:
                criteria[criterion_id] = CriterionAssessment(
                    criterion_id=criterion_id, assessed=False, score=None,
                    rationale="Not returned by the AI model.", evidence=[],
                )

    def _grounded_points(self, points: list[Point]) -> list[Point]:
        return [point for point in points if self._lines_near(point.timestamp)]

    def _is_grounded(self, evidence: Evidence) -> bool:
        for line in self._lines_near(evidence.timestamp):
            if self._quote_matches(evidence.quote, line.text):
                return True
        return False

    def _lines_near(self, timestamp: str) -> list[Cue]:
        """Spoken lines whose time range is within EVIDENCE_TOLERANCE_S of the timestamp."""
        seconds = parse_time(timestamp)
        if seconds is None:
            return []
        tolerance = config.EVIDENCE_TOLERANCE_S
        return [
            line for line in self.lines
            if not line.media and line.start - tolerance <= seconds <= line.end + tolerance
        ]

    @staticmethod
    def _quote_matches(quote: str, line_text: str) -> bool:
        """Exact (normalised) containment, or ≥ EVIDENCE_MIN_MATCH of the quote's characters found
        in order in runs of MIN_MATCH_RUN+ — tolerates small ASR-style differences."""
        quote, text = _normalise(quote), _normalise(line_text)
        if not quote:
            return False
        if quote in text:
            return True
        blocks = SequenceMatcher(None, quote, text, autojunk=False).get_matching_blocks()
        matched = sum(block.size for block in blocks if block.size >= MIN_MATCH_RUN)
        return matched / len(quote) >= config.EVIDENCE_MIN_MATCH


def _normalise(text: str) -> str:
    return " ".join(NON_WORD.sub(" ", text.casefold()).split())
