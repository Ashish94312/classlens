"""Calls Claude for the rubric assessment (HLD §7, LLD §5.10)."""

from dataclasses import dataclass

from classlens import config
from classlens.llm.claude import CallStats, StructuredCall
from classlens.llm.evidence import EvidenceValidator, ValidationResult
from classlens.llm.schema import Judgement
from classlens.models import Payload
from classlens.runlog import RunLog


@dataclass(frozen=True)
class JudgeResult:
    judgement: Judgement  # evidence already validated
    evidence_counts: dict[str, tuple[int, int]]  # criterion id → (accepted, rejected)
    trace: dict  # metadata for the UI's AI trace panel and the runtime log


class ClaudeJudge:
    """The rubric judgement: one structured call, then the evidence check."""

    def __init__(self, client=None, log: RunLog | None = None):
        self._call = StructuredCall("judge", config.PROMPT_VERSION, config.EFFORT, client, log)

    def assess(self, payload: Payload) -> JudgeResult:
        """Raises AIUnavailable if no answer could be obtained."""
        raw, stats = self._call.run(payload.text, Judgement)
        validation = EvidenceValidator(payload.lines).validate(raw)
        trace = self._trace(stats, validation)
        self._call.log.record("judge", "ok", trace)
        return JudgeResult(validation.judgement, validation.counts, trace)

    @staticmethod
    def _trace(stats: CallStats, validation: ValidationResult) -> dict:
        accepted = sum(counts[0] for counts in validation.counts.values())
        rejected = sum(counts[1] for counts in validation.counts.values())
        return {
            **stats.as_dict(),
            "evidence_accepted": accepted,
            "evidence_rejected": rejected,
            "holistic_grade": validation.judgement.holistic_grade,
            "transcript_quality": validation.judgement.transcript_quality,
        }
