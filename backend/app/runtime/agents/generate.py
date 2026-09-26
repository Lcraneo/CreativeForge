"""Generate Agent (Phase 16.6): initial asset creation only.

Image generation + style control via the Windup adapter. It does not know
DNA, animation or hitboxes exist.
"""

from typing import Any

from app.tools.generate_tool import GenerateTool
from app.runtime.agents.base import BaseAgent


class GenerateAgent(BaseAgent):
    name = "GenerateAgent"
    task = "generate_asset"

    def __init__(self, tool: GenerateTool | None = None):
        self.tool = tool or GenerateTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
