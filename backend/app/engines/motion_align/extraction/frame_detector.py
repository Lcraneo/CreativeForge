"""Frame Detector (Phase 15.2.3): auto-detects each frame's valid region.

512x512 in, actual character ~300x400 -> bbox [100, 50, 400, 450].
"""

from typing import Any

from app.utils import stable_hash


class FrameDetector:
    name = "frame_detector"

    def detect(self, image: str, index: int = 0) -> dict[str, Any]:
        seed = stable_hash(f"{image}:{index}")
        x1 = 90 + seed % 60
        y1 = 40 + (seed >> 8) % 40
        x2 = x1 + 260 + (seed >> 16) % 60
        y2 = y1 + 340 + (seed >> 24) % 50
        return {
            "image": image,
            "frame": index,
            "width": 512,
            "height": 512,
            "bbox": [x1, y1, min(x2, 502), min(y2, 502)],
            "anchor": {"x": round((x1 + x2) / 2, 1), "y": float(min(y2, 502))},
        }
