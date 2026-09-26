"""Transform primitives (Phase 15.1.5-7).

P' = P - (R_i - R)          translation
scale = targetHeight/currentHeight   normalization about a pivot
theta = atan2(y2-y1, x2-x1)         rotation via rotation matrix
"""

import math
from dataclasses import replace

from app.engines.motion_align.models.pose import (
    PosePoint,
    calculate_root,
    feet_center,
)


def translate_pose(
    points: dict[str, PosePoint], dx: float, dy: float
) -> dict[str, PosePoint]:
    return {
        name: replace(p, x=round(p.x + dx, 3), y=round(p.y + dy, 3))
        for name, p in points.items()
    }


def translate_frame(
    points: dict[str, PosePoint], target_root: tuple[float, float]
) -> tuple[dict[str, PosePoint], tuple[float, float]]:
    current_root = calculate_root(points)
    dx = target_root[0] - current_root[0]
    dy = target_root[1] - current_root[1]
    return translate_pose(points, dx, dy), (round(dx, 3), round(dy, 3))


def pose_height(points: dict[str, PosePoint]) -> float:
    head = points.get("head")
    if head is None:
        return 0.0
    fx, fy = feet_center(points)
    return abs(head.y - fy)


def normalize_scale(
    points: dict[str, PosePoint], target_height: float, pivot: tuple[float, float]
) -> tuple[dict[str, PosePoint], float]:
    current_height = pose_height(points)
    if current_height <= 0:
        return points, 1.0
    scale = target_height / current_height
    scaled = {
        name: replace(
            p,
            x=round(pivot[0] + (p.x - pivot[0]) * scale, 3),
            y=round(pivot[1] + (p.y - pivot[1]) * scale, 3),
        )
        for name, p in points.items()
    }
    return scaled, round(scale, 4)


def calculate_angle(hip: PosePoint, head: PosePoint) -> float:
    return math.atan2(head.y - hip.y, head.x - hip.x)


def rotate_pose(
    points: dict[str, PosePoint], delta_angle: float, pivot: tuple[float, float]
) -> dict[str, PosePoint]:
    cos_a, sin_a = math.cos(delta_angle), math.sin(delta_angle)
    rotated = {}
    for name, p in points.items():
        dx, dy = p.x - pivot[0], p.y - pivot[1]
        rotated[name] = replace(
            p,
            x=round(pivot[0] + dx * cos_a - dy * sin_a, 3),
            y=round(pivot[1] + dx * sin_a + dy * cos_a, 3),
        )
    return rotated
