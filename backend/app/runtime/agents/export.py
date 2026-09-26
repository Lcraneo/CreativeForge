"""Export Agent (Phase 16.11): engine adaptation.

Takes the complete CreativeAsset and hands it to GImport (Phase 15.4).
"""

from typing import Any

from app.tools.gimport_tool import GImportTool
from app.runtime.agents.base import BaseAgent


class ExportAgent(BaseAgent):
    name = "ExportAgent"
    task = "gimport"

    def __init__(self, tool: GImportTool | None = None):
        self.tool = tool or GImportTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
