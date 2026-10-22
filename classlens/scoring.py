"""The final grade: rubric criterion scores → weighted 0–100 score → Poor / Average / Good / Excellent
(HLD §6.3, LLD §5.18). Pure code, so the same scores always give the same grade."""

from classlens import config
from classlens.llm.schema import Judgement
from classlens.models import GradeResult


class Scorer:
    """score = 100 × Σ weight × (criterion score − 1) / 3 ÷ Σ weight, over the assessed criteria only,
    so a criterion the recording can't show doesn't count against the teacher."""

    def grade(self, judgement: Judgement) -> GradeResult:
        total_weight = sum(weight for _, weight in config.CRITERIA.values())
        weighted, assessed_weight = 0.0, 0
        for criterion in judgement.criteria:
            if not criterion.assessed or criterion.score is None:
                continue
            weight = config.CRITERIA[criterion.criterion_id][1]
            weighted += weight * (criterion.score - 1) / 3
            assessed_weight += weight
        if assessed_weight == 0:
            return GradeResult("Poor", 0.0, 0.0, provisional=True)
        score = 100 * weighted / assessed_weight
        share = assessed_weight / total_weight
        return GradeResult(self._band(score), round(score, 1), round(share, 2), share < config.PROVISIONAL_MIN_WEIGHT)

    @staticmethod
    def _band(score: float) -> str:
        for minimum, grade in config.GRADE_BANDS:
            if score >= minimum:
                return grade
        return config.GRADE_BANDS[-1][1]
