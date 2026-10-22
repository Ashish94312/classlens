"""The final grade: rubric criterion scores → weighted 0–100 score → Poor / Average / Good / Excellent
(HLD §6.3, LLD §5.18). Pure code, so the same scores always give the same grade."""

from classlens import config
from classlens.llm.schema import Judgement
from classlens.models import GradeResult, VideoFindings

GRADE_ORDER = [grade for _, grade in reversed(config.GRADE_BANDS)]  # Poor … Excellent


class Scorer:
    """score = 100 × Σ weight × (criterion score − 1) / 3 ÷ Σ weight, over the assessed criteria only,
    so a criterion the recording can't show doesn't count against the teacher. With video findings,
    C6 and C7 also use the video checks, and video gates can cap the grade."""

    def grade(self, judgement: Judgement, video: VideoFindings | None = None) -> GradeResult:
        scores = self.criterion_scores(judgement, video)
        total_weight = sum(weight for _, weight in config.CRITERIA.values())
        weighted, assessed_weight = 0.0, 0
        for criterion_id, score in scores.items():
            weight = config.CRITERIA[criterion_id][1]
            weighted += weight * (score - 1) / 3
            assessed_weight += weight
        if assessed_weight == 0:
            return GradeResult("Poor", 0.0, 0.0, provisional=True)
        score = 100 * weighted / assessed_weight
        share = assessed_weight / total_weight
        flags = gate_flags(video)
        grade = _cap(self._band(score), len(flags))
        return GradeResult(grade, round(score, 1), round(share, 2), share < config.PROVISIONAL_MIN_WEIGHT, flags)

    @staticmethod
    def criterion_scores(judgement: Judgement, video: VideoFindings | None) -> dict[str, float]:
        """Assessed criterion id → score 1–4. C6: the lower of Claude's (from what the transcript
        shows) and the video's, so either source's problem counts. C7: the mean of the two."""
        scores = {}
        for criterion in judgement.criteria:
            if criterion.assessed and criterion.score is not None:
                scores[criterion.criterion_id] = float(criterion.score)
        if video is None:
            return scores
        presence = presence_score(video)
        if presence is not None:
            scores["C6"] = min(scores.get("C6", presence), presence)
        technical = technical_score(video)
        if technical is not None:
            scores["C7"] = (scores.get("C7", technical) + technical) / 2
        return scores

    @staticmethod
    def _band(score: float) -> str:
        for minimum, grade in config.GRADE_BANDS:
            if score >= minimum:
                return grade
        return config.GRADE_BANDS[-1][1]


def presence_score(video: VideoFindings) -> int | None:
    """C6 from the video, 1–4: one point off for each problem (camera off, face not visible, each
    at two levels; poor light). None in gallery view, where the teacher can't be singled out."""
    if video.gallery > config.GALLERY_MAX:
        return None
    problems = 0
    if video.camera_off > config.CAMERA_OFF_MINOR:
        problems += 1
    if video.camera_off > config.CAMERA_OFF_GATE:
        problems += 1
    if video.face_visible is not None and video.face_visible < config.FACE_VISIBLE_MINOR:
        problems += 1
    if video.face_visible is not None and video.face_visible < config.FACE_VISIBLE_GATE:
        problems += 1
    if video.low_light is not None and video.low_light > config.LOW_LIGHT_MAX:
        problems += 1
    return max(1, 4 - problems)


def technical_score(video: VideoFindings) -> int | None:
    """C7 from the video, 2–4: one point off for frequent freezes, one for a blurred picture. None
    when no speaker-view frame with a face was found."""
    if video.frozen is None:
        return None
    problems = 0
    if video.frozen > config.FROZEN_MAX:
        problems += 1
    if video.blurry > config.BLURRY_MAX:
        problems += 1
    return 4 - problems


def gate_flags(video: VideoFindings | None) -> tuple[str, ...]:
    """Critical problems from the "known quality issue" classes (HLD §6.3), as report lines."""
    if video is None or video.gallery > config.GALLERY_MAX:
        return ()
    flags = []
    if video.camera_off > config.CAMERA_OFF_GATE:
        flags.append(f"Teacher's camera off in {video.camera_off:.0%} of the moments checked "
                     f"(limit {config.CAMERA_OFF_GATE:.0%})")
    if video.face_visible is not None and video.face_visible < config.FACE_VISIBLE_GATE:
        flags.append(f"Teacher's face visible in only {video.face_visible:.0%} of camera-on moments "
                     f"(minimum {config.FACE_VISIBLE_GATE:.0%})")
    return tuple(flags)


def best_allowed(flag_count: int) -> str:
    """The best grade a class with this many gate flags can get: one → Average, two or more → Poor."""
    if flag_count == 0:
        return GRADE_ORDER[-1]
    return config.GATE_CAPS[min(flag_count, max(config.GATE_CAPS))]


def _cap(grade: str, flag_count: int) -> str:
    return min(grade, best_allowed(flag_count), key=GRADE_ORDER.index)
