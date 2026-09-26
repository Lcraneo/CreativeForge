"""MotionAlign pipeline (Phase 15.1.11 / 15.2 / 15.3 / 15.5.16):

    AI Animation Frames
        -> Pose Detection -> Keypoints
        -> Anchor Solver  -> Aligned Frames      (root / scale / rotation)
        -> Frame Extraction -> Sprite resources  (crop + anchor padding)
        -> Sprite Sheet / Atlas
        -> Animation Timeline + events + states
        -> Hitbox / Hurtbox
        -> CreativeAsset.Animation

Writes the CreativeAsset Animation contract: frames / anchor / motion /
action (+ timeline, atlas, clips, states, graph, combat).
"""

import re
from pathlib import PurePosixPath
from typing import Any

from app.engines.motion_align.alignment.anchor_solver import AnchorSolver
from app.engines.motion_align.collision.hitbox_generator import HitboxGenerator
from app.engines.motion_align.detector.pose_detector import PoseDetector
from app.engines.motion_align.extraction.frame_detector import FrameDetector
from app.engines.motion_align.extraction.sprite_cropper import SpriteCropper
from app.engines.motion_align.models.frame import Frame
from app.engines.motion_align.sprite.atlas import AtlasGenerator
from app.engines.motion_align.sprite.normalizer import PaddingNormalizer
from app.engines.motion_align.timeline.animation_builder import AnimationBuilder
from app.engines.motion_align.timeline.event import build_events
from app.engines.motion_align.timeline.graph import AnimationGraph
from app.engines.motion_align.timeline.state_machine import (
    AnimationStateMachine,
    default_states,
)

ATTACK_KEYWORDS = ("攻击", "挥剑", "斩", "attack", "slash")


class MotionAlignProcessor:
    name = "motion_align"

    def __init__(
        self,
        fps: int = 12,
        frame_count: int = 8,
        frame_size: int = 128,
        target_root: tuple[float, float] = (256.0, 400.0),
        target_height: float = 300.0,
        hitbox_expand: float = 8.0,
    ):
        self.fps = fps
        self.frame_count = frame_count
        self.frame_size = frame_size
        self.target_root = target_root
        self.target_height = target_height
        self.detector = PoseDetector()
        self.solver = AnchorSolver(target_root=target_root, target_height=target_height)
        self.frame_detector = FrameDetector()
        self.cropper = SpriteCropper()
        self.normalizer = PaddingNormalizer(frame_size=(frame_size, frame_size))
        self.atlas = AtlasGenerator()
        self.animation_builder = AnimationBuilder()
        self.state_machine_factory = AnimationStateMachine
        self.graph_builder = AnimationGraph()
        self.hitbox_generator = HitboxGenerator(expand_radius=hitbox_expand)

    async def process(self, asset: dict[str, Any]) -> dict[str, Any]:
        stem = PurePosixPath(asset["content"]["image"]).stem
        goal = str((asset.get("identity") or {}).get("prompt") or "")
        action = "attack" if any(k in goal.lower() for k in ATTACK_KEYWORDS) else "idle"

        target_height = self._dna_aware_height(asset)

        # 1-2. frame sources + pose keypoints
        frames = [
            Frame(index=i, image=f"{stem}_{i + 1:03d}.png")
            for i in range(self.frame_count)
        ]
        for frame in frames:
            frame.pose = await self.detector.detect(frame.image, frame.index)

        # 3. anchor alignment (translation + scale + rotation)
        self.solver.target_height = target_height
        frames, stats = self.solver.align(frames)

        # 4-5. valid-region detection, crop, anchor-based padding
        sprites = []
        for frame in frames:
            region = self.frame_detector.detect(frame.image, frame.index)
            frame.bbox = region["bbox"]
            cropped = self.cropper.crop(frame.image, region)
            sprite = self.normalizer.normalize(
                cropped, anchor=(region["anchor"]["x"], region["anchor"]["y"])
            )
            sprite["name"] = f"{stem}_{action}_{frame.index + 1:03d}"
            frame.sprite = sprite["name"]
            sprites.append(sprite)

        # 6. atlas
        atlas = self.atlas.generate(sprites, texture=f"{stem}_atlas.png")

        # 7. timeline + events + states + graph
        events = build_events(action, len(sprites), fps=self.fps)
        timeline = self.animation_builder.build(action, sprites, fps=self.fps, events=events)
        machine = self.state_machine_factory(default_states(action))
        graph = self.graph_builder.build(default_states(action))

        # 8. hitbox / hurtbox (needs AssetStruct layers + events)
        combat = await self.hitbox_generator.generate(
            asset, events=events, frame_count=len(sprites)
        )

        # 9. write the CreativeAsset Animation contract
        asset["animation"] = {
            "frames": [
                {
                    "id": frame.index,
                    "uri": frame.sprite,
                    "duration": round(1000 / self.fps),
                }
                for frame in frames
            ],
            "anchor": {"root": {"x": self.target_root[0], "y": self.target_root[1]}},
            "motion": {
                "root_dx": 0,
                "root_dy": 0,
                "max_root_residual": stats["max_root_residual"],
            },
            "action": action,
            "timeline": timeline,
            "atlas": atlas["texture"],
            "atlas_detail": atlas,
            "clips": [timeline],
            "states": machine.to_dict(),
            "graph": graph,
        }
        asset["combat"] = combat
        return asset

    def _dna_aware_height(self, asset: dict[str, Any]) -> float:
        """Phase 15.1.9: keep THIS character's proportions, not a global one."""
        dna = asset.get("dna") or {}
        ratio = ((dna.get("identity") or {}).get("body") or {}).get("height_ratio")
        if not ratio:
            return self.target_height
        clamped = min(max(ratio, 0.5), 2.0)
        return round(self.target_height * clamped, 2)
