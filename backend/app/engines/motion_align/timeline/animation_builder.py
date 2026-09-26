"""Animation Builder (Phase 15.2.9 / 15.3): sprites -> game timeline.

    0s frame1 | 0.08s frame2 | 0.16s frame3 ...
"""

from typing import Any

from app.engines.motion_align.timeline.clip import AnimationClip
from app.engines.motion_align.timeline.event import build_events


class AnimationBuilder:
    def build(
        self,
        name: str,
        sprites: list[dict[str, Any]],
        fps: int = 12,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        duration_ms = round(1000 / fps)
        frames = [
            {
                "id": index,
                "time": round(index / fps, 3),
                "sprite": sprite["name"],
                "uri": sprite["source"],
                "duration": duration_ms,
            }
            for index, sprite in enumerate(sprites)
        ]
        clip = AnimationClip(
            name=name,
            fps=fps,
            frames=frames,
            events=events if events is not None else build_events(name, len(sprites), fps),
        )
        return clip.to_dict()
