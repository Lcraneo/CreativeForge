"""Frame Analyzer (Phase 15.2.3): per-frame size / bbox / anchor metadata."""

from typing import Any


class FrameAnalyzer:
    def analyze(self, frame: dict[str, Any]) -> dict[str, Any]:
        bbox = frame.get("bbox") or [0, 0, 0, 0]
        return {
            "image": frame.get("image"),
            "width": frame.get("size", [0, 0])[0],
            "height": frame.get("size", [0, 0])[1],
            "bbox": bbox,
            "anchor": frame.get("anchor") or {"x": 0.0, "y": 0.0},
        }
