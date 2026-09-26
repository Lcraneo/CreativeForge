"""Simulation Agent (Phase 23.8): playtests the produced logic and repairs it."""

from typing import Any

from app.tools.simulate_tool import SimulationTool
from app.runtime.agents.base import BaseAgent


class SimulationAgent(BaseAgent):
    name = "SimulationAgent"
    task = "simulate"

    def __init__(self, tool: SimulationTool | None = None):
        self.tool = tool or SimulationTool()

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.tool.run(context)
