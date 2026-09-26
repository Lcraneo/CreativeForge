"""Anchor Solver (Phase 15.1.4 / 15.1.8) — the core of MotionAlign.

Finds the shared reference across frames and rewrites every frame onto it:
root translation -> scale normalization -> rotation alignment, all about the
root pivot so the three corrections never fight each other.
"""

import math
from typing import Any

from app.engines.motion_align.alignment.transform import (
    calculate_angle,
    normalize_scale,
    rotate_pose,
    translate_frame,
)
from app.engines.motion_align.models.frame import Frame
from app.engines.motion_align.models.pose import (
    UPRIGHT_ANGLE,
    calculate_root,
)


class AnchorSolver:
    def __init__(
        self,
        target_root: tuple[float, float] = (256.0, 400.0),
        target_height: float = 300.0,
    ):
        self.target_root = target_root
        self.target_height = target_height

    def solve_root(self, frames: list[Frame]) -> tuple[float, float]:
        """Mean root over all frames: R = 1/N * sum(R_i)."""
        if not frames:
            return self.target_root
        roots = [calculate_root(f.pose) for f in frames]
        return (
            sum(r[0] for r in roots) / len(roots),
            sum(r[1] for r in roots) / len(roots),
        )

    def align_root(self, pose, target_root=None):
        return translate_frame(pose, target_root or self.target_root)

    def normalize(self, pose, target_height=None, pivot=None):
        pivot = pivot or self.target_root
        return normalize_scale(pose, target_height or self.target_height, pivot)

    def solve_rotation(self, pose) -> float:
        """Delta that brings the hip -> head axis back upright."""
        hip, head = pose.get("hip"), pose.get("head")
        if hip is None or head is None:
            return 0.0
        return UPRIGHT_ANGLE - calculate_angle(hip, head)

    def align(self, frames: list[Frame]) -> tuple[list[Frame], dict[str, Any]]:
        residuals = []
        for frame in frames:
            pose, (dx, dy) = self.align_root(frame.pose)
            pose, scale = self.normalize(pose, pivot=self.target_root)
            delta_angle = self.solve_rotation(pose)
            pose = rotate_pose(pose, delta_angle, self.target_root)

            frame.pose = pose
            frame.correction = {
                "dx": dx,
                "dy": dy,
                "scale": scale,
                "rotation_rad": round(delta_angle, 4),
            }
            residuals.append(
                max(
                    abs(calculate_root(pose)[0] - self.target_root[0]),
                    abs(calculate_root(pose)[1] - self.target_root[1]),
                )
            )
        stats = {
            "target_root": list(self.target_root),
            "target_height": self.target_height,
            "max_root_residual": round(max(residuals, default=0.0), 4),
            "aligned_frames": len(frames),
        }
        return frames, stats
