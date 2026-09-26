"""Animation frame model (Phase 15.1.11)."""

from dataclasses import dataclass, field
from typing import Any

from app.engines.motion_align.models.pose import PosePoint


@dataclass
class Frame:
    index: int
    image: str
    pose: dict[str, PosePoint] = field(default_factory=dict)
    bbox: list[float] | None = None
    sprite: str | None = None
    correction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "image": self.image,
            "sprite": self.sprite,
            "bbox": self.bbox,
            "pose": {name: p.to_dict() for name, p in self.pose.items()},
            "correction": self.correction,
        }
