"""Game Logic Agent (Phase 23.6): skill design + numbers + event binding."""

from typing import Any

from app.tools.logic_tool import GameLogicTool
from app.runtime.agents.base import BaseAgent


class GameLogicAgent(BaseAgent):
    name = "GameLogicAgent"
    task = "create_logic"

    def __init__(self, tool: GameLogicTool | None = None):
        self.tool = tool or GameLogicTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
