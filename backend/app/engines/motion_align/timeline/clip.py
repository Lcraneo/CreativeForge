"""AnimationClip (Phase 15.3.3): when does what happen."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnimationClip:
    name: str
    fps: int = 12
    frames: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(len(self.frames) / self.fps, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fps": self.fps,
            "duration": self.duration,
            "frames": self.frames,
            "events": self.events,
        }
