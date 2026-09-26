"""Motion Agent (Phase 16.9): animation production.

Animation alignment -> pose correction -> sprite extraction -> timeline,
via the Phase 15 MotionAlign engine. Action choice comes from the intent,
seeded by the animation knowledge library (Phase 19.11).
"""

from typing import Any

from app.engines.foundation.animation_library import resolve_action
from app.tools.motion_tool import MotionAlignTool
from app.runtime.agents.base import BaseAgent


class MotionAgent(BaseAgent):
    name = "MotionAgent"
    task = "motion_align"

    def __init__(self, tool: MotionAlignTool | None = None):
        self.tool = tool or MotionAlignTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        intent = context.get("intent") or {}
        context["action"] = resolve_action(intent.get("actions") or [])
        return await self.tool.run(context)
