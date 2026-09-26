"""Human-in-the-loop (Phase 17.10): production assets need review gates.

    Concept Review    after Generate (character design)
    Animation Review  after Motion (action quality)
    Runtime Review    after Export (engine loading)

A paused task sits in WAITING_REVIEW with a full checkpoint; the approve
endpoint resumes it from exactly that node.
"""

from typing import Any

REVIEW_TYPES = {
    "generate_asset": "concept_review",
    "motion_align": "animation_review",
    "gimport": "runtime_review",
}


def review_points_for(review: bool | list[str] | None) -> list[str]:
    if review is True:
        return ["generate_asset"]
    if isinstance(review, list):
        return [point for point in review if point in REVIEW_TYPES]
    return []


def review_type(node_id: str) -> str | None:
    return REVIEW_TYPES.get(node_id)
