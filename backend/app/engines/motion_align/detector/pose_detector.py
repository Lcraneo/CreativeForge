"""Pose detection (Phase 15.1.2).

MVP: deterministic pseudo MediaPipe Pose. Builds a base skeleton from the
frame id, then injects the five AI drift classes (root / scale / rotation /
limb / camera) per frame so the AnchorSolver has real misalignment to
correct. Replace `detect` with the MediaPipe / OpenPose call later.
"""

import math
from typing import Any

from app.engines.motion_align.models.pose import PosePoint
from app.utils import stable_hash


def _rotate(x: float, y: float, px: float, py: float, angle: float) -> tuple[float, float]:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = x - px, y - py
    return (px + dx * cos_a - dy * sin_a, py + dx * sin_a + dy * cos_a)


class PoseDetector:
    name = "pose_detector"

    async def detect(self, image: str, frame_index: int = 0) -> dict[str, PosePoint]:
        seed = stable_hash(image)
        root_x = 220 + seed % 80
        root_y = 380 + (seed >> 6) % 40
        skeleton = {
            "head": (root_x + ((seed >> 3) % 9) - 4, root_y - 240),
            "shoulder": (root_x, root_y - 180),
            "hip": (root_x, root_y - 110),
            "hand": (root_x + 40 + ((seed >> 9) % 20), root_y - 150),
            "left_foot": (root_x - 18, root_y),
            "right_foot": (root_x + 18, root_y),
        }

        wobble = stable_hash(f"{image}#{frame_index}")
        dx = (wobble % 17) - 8
        dy = ((wobble >> 5) % 17) - 8
        scale = 1.0 + (((wobble >> 10) % 13) - 6) / 100.0
        rotation = (((wobble >> 15) % 7) - 3) * math.pi / 180.0

        points: dict[str, PosePoint] = {}
        for name, (x, y) in skeleton.items():
            sx, sy = root_x + (x - root_x) * scale, root_y + (y - root_y) * scale
            rx, ry = _rotate(sx, sy, root_x, root_y, rotation)
            confidence = 0.9 + ((wobble >> (20 + len(name))) % 10) / 100.0
            points[name] = PosePoint(
                name=name, x=round(rx + dx, 2), y=round(ry + dy, 2), confidence=round(confidence, 3)
            )
        return points

    def describe(self) -> dict[str, Any]:
        return {"model": "pseudo-mediapipe", "points": ["head", "shoulder", "hip", "hand", "left_foot", "right_foot"]}
