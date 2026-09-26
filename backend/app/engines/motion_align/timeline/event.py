"""Animation events (Phase 15.3.8-9, Phase 15.5.9-10).

Not every frame of a 10 frame attack deals damage — only frame 6. Events
bind gameplay meaning (sound / vfx / damage / hitbox window) to frames.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class AnimationEvent:
    frame: int
    type: str
    value: Any = None

    def with_time(self, fps: int) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "time": round(self.frame / fps, 3),
            "type": self.type,
            "value": self.value,
        }


def active_window(frame_count: int) -> tuple[int, int]:
    """Frames where the hitbox is enabled (attack contact window)."""
    start = max(2, int(frame_count * 0.5))
    end = min(frame_count, start + max(1, frame_count // 4))
    return start, end


def build_events(clip_name: str, frame_count: int, fps: int = 12) -> list[dict[str, Any]]:
    events: list[AnimationEvent] = []
    if clip_name == "attack":
        start, end = active_window(frame_count)
        events.extend(
            [
                AnimationEvent(max(1, start - 1), "sound", "sword.wav"),
                AnimationEvent(start, "effect", "fire"),
                AnimationEvent(start, "damage", 100),
                AnimationEvent(start, "hitbox_enable", "fire_sword"),
                AnimationEvent(min(frame_count, end + 1), "hitbox_disable", "fire_sword"),
                AnimationEvent(frame_count, "recover", None),
            ]
        )
    else:
        events.append(AnimationEvent(max(1, frame_count // 2), "sound", "step.wav"))
    return [event.with_time(fps) for event in events]
