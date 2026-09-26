"""Tool Router (Phase 11): executes a plan step by step.

Every step receives one shared mutable context dict, so tools can hand the
evolving CreativeAsset to each other (`context["asset"]`).
"""

from typing import Any

from app.tools.registry import ToolRegistry


class ToolRouter:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, plan: dict, context: dict) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for task in plan.get("tasks", []):
            tool = self.registry.get(task)
            if tool is None:
                results[task] = {"status": "skipped", "reason": "unknown tool"}
                continue
            results[task] = await tool.run(context)
        return results
