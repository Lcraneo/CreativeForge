"""DNA Agent (Phase 16.8): establish or extend the character identity.

Encoder -> Embedding -> Vector DB -> DNA record (+ six-layer profile,
Phase 19.4) via the Phase 14 service.
"""

from typing import Any

from app.tools.dna_tool import DnaTool
from app.runtime.agents.base import BaseAgent


class DNAAgent(BaseAgent):
    name = "DNAAgent"
    task = "create_dna"

    def __init__(self, tool: DnaTool | None = None):
        self.tool = tool or DnaTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
