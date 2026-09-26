"""Motion Align Tool (Phase 15.1.12): route motion_align to the engine."""

from typing import Any

from app.core.config import settings
from app.engines.motion_align.pipeline.processor import MotionAlignProcessor
from app.tools.base import BaseTool


class MotionAlignTool(BaseTool):
    name = "motion_align"

    def __init__(self, processor: MotionAlignProcessor | None = None):
        self.processor = processor or MotionAlignProcessor(
            fps=settings.DEFAULT_FPS,
            frame_count=settings.FRAME_COUNT,
            frame_size=settings.FRAME_SIZE,
            target_root=settings.target_root,
            target_height=settings.TARGET_HEIGHT,
            hitbox_expand=settings.HITBOX_EXPAND_RADIUS,
        )

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        asset = await self.processor.process(context["asset"])
        context["asset"] = asset
        animation = asset["animation"]
        return {
            "action": animation["action"],
            "frames": len(animation["frames"]),
            "atlas": animation["atlas"],
            "max_root_residual": animation["motion"]["max_root_residual"],
        }
