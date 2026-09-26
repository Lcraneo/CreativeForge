"""Pose keypoint data structure (Phase 15.1.2).

One unified keypoint vocabulary for every frame; anchors used by the
solver are hip / left_foot / right_foot / head (multi-point so translation,
scale AND rotation can be solved — a single root cannot).
"""

from dataclasses import asdict, dataclass

ANCHOR_POINTS = ["hip", "left_foot", "right_foot", "head"]

# Vertical-up direction in screen coordinates (y grows downwards).
UPRIGHT_ANGLE = -1.5707963267948966  # -pi/2


@dataclass
class PosePoint:
    name: str
    x: float
    y: float
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def points_from(data: dict) -> dict[str, PosePoint]:
    return {
        name: PosePoint(name=name, **coords) for name, coords in data.items()
    }


def calculate_root(
    points: dict[str, PosePoint], anchors: list[str] | None = None
) -> tuple[float, float]:
    """R = 1/N * sum(R_i): the shared reference across all frames."""
    selected = [points[name] for name in (anchors or ANCHOR_POINTS) if name in points]
    if not selected:
        selected = list(points.values()) or [PosePoint("root", 0.0, 0.0)]
    x = sum(p.x for p in selected) / len(selected)
    y = sum(p.y for p in selected) / len(selected)
    return (x, y)


def feet_center(points: dict[str, PosePoint]) -> tuple[float, float]:
    feet = [points[n] for n in ("left_foot", "right_foot") if n in points]
    if not feet:
        hip = points.get("hip") or PosePoint("hip", 0.0, 0.0)
        return (hip.x, hip.y)
    return (
        sum(p.x for p in feet) / len(feet),
        sum(p.y for p in feet) / len(feet),
    )
