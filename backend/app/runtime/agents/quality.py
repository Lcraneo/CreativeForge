"""Quality Agent (Phase 16.17): the final gate.

Checks the four quality planes and returns machine-readable issues the
Planner can act on (self healing):

    structural  layers complete / graph rooted
    dna         identity present
    motion      anchor drift below threshold
    runtime     engine manifest complete
"""

from typing import Any

from app.runtime.agents.base import BaseAgent

MOTION_RESIDUAL_LIMIT = 1.0


class QualityAgent(BaseAgent):
    name = "QualityAgent"
    task = "quality_check"

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        asset = context.get("asset") or {}
        issues: list[dict[str, Any]] = []

        content = asset.get("content") or {}
        layers = content.get("layers") or []
        if not layers:
            issues.append({"plane": "structural", "error": "no_layers", "suggestion": "rerun_structure"})
        elif not (content.get("graph") or {}).get("id"):
            issues.append({"plane": "structural", "error": "graph_unrooted", "suggestion": "rerun_structure"})

        if not asset.get("dna"):
            issues.append({"plane": "dna", "error": "missing_identity", "suggestion": "rerun_dna"})

        animation = asset.get("animation") or {}
        residual = ((animation.get("motion") or {}).get("max_root_residual"))
        if residual is None:
            issues.append({"plane": "motion", "error": "pose_unstable", "suggestion": "rerun_motion"})
        elif residual > MOTION_RESIDUAL_LIMIT:
            issues.append(
                {
                    "plane": "motion",
                    "error": "anchor_drift",
                    "value": residual,
                    "suggestion": "rerun_motion",
                }
            )

        engine = asset.get("engine") or {}
        manifest = ((engine.get("resources") or {}).get("quality") or {}).get("manifest_score")
        if manifest is None or manifest < 1.0:
            issues.append({"plane": "runtime", "error": "manifest_incomplete", "suggestion": "rerun_export"})

        return {"passed": not issues, "issues": issues, "score": self.score(asset)}

    @staticmethod
    def score(asset: dict[str, Any]) -> float:
        quality = asset.get("quality") or {}
        parts = [
            quality.get("segmentation_score"),
            quality.get("import"),
        ]
        values = [p for p in parts if isinstance(p, (int, float))]
        return round(sum(values) / len(values), 4) if values else 0.0
