DEFAULT_ANCHOR = {
    "root": {"x": 32, "y": 60},
    "feet": {"x": 32, "y": 64},
    "center": {"x": 32, "y": 40},
    "head": {"x": 32, "y": 8}
}


class AnchorDetector:
    """Detects stable character keypoints (root / feet / center / head) per frame.

    Skeleton behaviour: uses upstream keypoint hints carried on the frame when
    a keypoint model already ran, and fills missing points with defaults.
    """

    def detect(self, frames):
        return [self._detect_frame(frame) for frame in frames]

    def _detect_frame(self, frame):
        hint = frame.get("anchor") or {}
        detected = {}
        for point, default in DEFAULT_ANCHOR.items():
            detected[point] = dict(hint.get(point) or default)
        return detected
