"""Domain agents (Phase 16.3): each owns one specialty and nothing else.

The Generate agent must not know about hitboxes; the Combat agent must not
generate characters. Agents wrap the frozen Phase 11-15 tools, so the
engines stay the single source of truth.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    name: str
    task: str

    @abstractmethod
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's specialty over the shared pipeline context."""
        raise NotImplementedError
