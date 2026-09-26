"""Simulation Tool (Phase 23.9): route simulate to the engine."""

from typing import Any

from app.engines.foundation.simulation import simulate_asset
from app.tools.base import BaseTool


class SimulationTool(BaseTool):
    name = "simulate"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        asset = context.get("asset")
        if not asset:
            return {"status": "skipped", "reason": "no asset to simulate"}

        report = simulate_asset(asset)
        context.setdefault("decisions", []).append(
            f"simulation: {report['repairs']} auto-repair(s), score {report['score']}"
        )
        return {
            "passed": report["passed"],
            "repairs": report["repairs"],
            "score": report["score"],
            "issues": report["issues"][:5],
            "checks": report["checks"],
        }
