"""Tool abstraction (Phase 11.8): every capability is a plugin.

Later capabilities (Windup / SAM2 / MotionAlign / ...) only need to
register themselves, never to change the pipeline.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str

    @abstractmethod
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool. `params` is the shared pipeline context."""
        raise NotImplementedError
