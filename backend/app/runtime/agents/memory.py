"""Memory Agent (Phase 16.12): asset memory search before anything else.

Finds whether the goal refers to an existing character, so the Planner can
skip full generation and run an identity-preserving modification instead.
"""

from typing import Any

from app.tools.search_tool import CharacterSearchTool, detect_changes
from app.runtime.agents.base import BaseAgent


class MemoryAgent(BaseAgent):
    name = "MemoryAgent"
    task = "find_character"

    def __init__(self, tool: CharacterSearchTool | None = None):
        self.tool = tool or CharacterSearchTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        result = await self.tool.run(context)
        if result.get("found"):
            context.setdefault("decisions", []).append(
                f"asset memory hit: {result['id']} -> identity-preserving modification"
            )
        else:
            context.setdefault("decisions", []).append(
                "asset memory miss -> full creation pipeline"
            )
        return result
