"""Style Agent (Phase 22.1): the Dynamic Planner's style-only capability.

Chosen for `change=style` goals instead of the full generation pipeline;
carries the previous version forward with a palette edit.
"""

from typing import Any

from app.tools.style_tool import StyleTool
from app.runtime.agents.base import BaseAgent


class StyleAgent(BaseAgent):
    name = "StyleAgent"
    task = "modify_style"

    def __init__(self, tool: StyleTool | None = None):
        self.tool = tool or StyleTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
