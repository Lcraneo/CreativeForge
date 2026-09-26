"""Agent Self Evaluation (Phase 22.4): every result carries a confidence.

Each agent summary is augmented with a deterministic confidence score
extracted from the signals it already produces (segmentation score, motion
residual, manifest score, ...). The executor treats a summary below
`CONFIDENCE_FLOOR` like a failed quality gate: the offending nodes rerun
once (self healing), then the task fails loud — never silently ships a
dubious asset.
"""

from typing import Any

CONFIDENCE_FLOOR = 0.8


def confidence_from_summary(node: str, summary: Any) -> float:
    """Map a node's summary onto [0, 1]; 1.0 when nothing measurable."""
    if not isinstance(summary, dict):
        return 1.0

    def _num(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None

    if node == "structure_asset":
        score = _num(summary.get("segmentation_score"))
        return round(score, 4) if score is not None else 1.0
    if node == "motion_align":
        residual = _num(summary.get("max_root_residual"))
        return round(max(0.0, 1.0 - residual), 4) if residual is not None else 1.0
    if node == "gimport":
        quality = summary.get("quality") or {}
        score = _num(quality.get("manifest_score")) if isinstance(quality, dict) else None
        return round(score, 4) if score is not None else 1.0
    if node == "combat":
        return 1.0 if summary.get("skill") else 0.4
    if node == "find_character":
        return 0.95 if summary.get("found") else 0.5
    if node == "modify_style":
        return 0.9 if summary.get("changed") else 0.5
    if node == "create_logic":
        return 0.9 if summary.get("skill") else 0.5
    if node == "simulate":
        if summary.get("passed") is False:
            return 0.5
        score = _num(summary.get("score"))
        return round(min(1.0, score), 4) if score is not None else 1.0
    if node == "quality_check":
        if summary.get("passed") is False:
            return 0.5
        score = _num(summary.get("score"))
        return round(min(1.0, score), 4) if score is not None else 1.0
    return 1.0


def low_confidence_nodes(result: dict[str, Any]) -> list[str]:
    """Nodes whose completed summary falls below the confidence floor."""
    return [
        node
        for node, summary in result.items()
        if isinstance(summary, dict)
        and isinstance(summary.get("confidence"), (int, float))
        and summary["confidence"] < CONFIDENCE_FLOOR
    ]


def evaluate_task_result(asset: dict[str, Any]) -> dict[str, Any]:
    """Task-level evaluation record (Phase 23.10): the three quality planes
    the spec's Agent Feedback Loop tracks:

        identity  version similarity (or presence of a DNA record)
        animation 1 - anchor drift residual
        engine    manifest completeness
    """
    dna = asset.get("dna") or {}
    similarity = dna.get("identity_similarity")
    identity = (
        round(float(similarity), 4)
        if isinstance(similarity, (int, float))
        else (1.0 if dna else 0.0)
    )
    residual = ((asset.get("animation") or {}).get("motion") or {}).get(
        "max_root_residual"
    )
    animation = (
        round(max(0.0, 1.0 - float(residual)), 4)
        if isinstance(residual, (int, float))
        else 1.0
    )
    manifest = (
        ((asset.get("engine") or {}).get("resources") or {}).get("quality") or {}
    ).get("manifest_score")
    engine = round(float(manifest), 4) if isinstance(manifest, (int, float)) else 0.0
    overall = round(0.4 * identity + 0.3 * animation + 0.3 * engine, 4)
    return {"identity": identity, "animation": animation, "engine": engine, "overall": overall}
