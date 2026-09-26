"""AssetStruct Agent (Phase 16.7): image -> game asset structure.

Layer separation, mask generation and the asset graph — the Phase 13
engine does the work, the agent owns the intent.
"""

from typing import Any

from app.tools.struct_tool import StructTool
from app.runtime.agents.base import BaseAgent


class AssetStructAgent(BaseAgent):
    name = "AssetStructAgent"
    task = "structure_asset"

    def __init__(self, tool: StructTool | None = None):
        self.tool = tool or StructTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
