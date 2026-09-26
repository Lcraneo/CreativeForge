"""Engine exporter interface (Phase 15.4.2).

    Exporter Interface
        +---- CocosExporter
        +---- UnityExporter   (Godot / Unreal plug in the same way)
"""

from abc import ABC, abstractmethod
from typing import Any


class EngineExporter(ABC):
    name: str

    @abstractmethod
    async def export(self, asset: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
