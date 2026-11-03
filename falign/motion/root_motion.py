DRIFT_THRESHOLD = 4.0


class RootMotionCorrector:
    """Classifies root delta between frames as real motion or drift.

    Average per-frame step below DRIFT_THRESHOLD is treated as character
    drift and corrected back to the frame-0 root; larger steps are kept as
    real root motion.
    """

    def correct(self, frames, anchors):
        roots = [anchor.get("root", {}) for anchor in anchors]
        if not roots:
            return {
                "root_dx": 0,
                "root_dy": 0,
                "drift_corrected": False,
                "real_motion": False,
                "root_track": [],
                "corrections": []
            }

        origin_x = roots[0].get("x", 0)
        origin_y = roots[0].get("y", 0)
        deltas = [
            {
                "dx": root.get("x", 0) - origin_x,
                "dy": root.get("y", 0) - origin_y
            }
            for root in roots
        ]

        steps = [
            abs(roots[index].get("x", 0) - roots[index - 1].get("x", 0))
            + abs(roots[index].get("y", 0) - roots[index - 1].get("y", 0))
            for index in range(1, len(roots))
        ]
        average_step = sum(steps) / len(steps) if steps else 0.0
        real_motion = average_step >= DRIFT_THRESHOLD

        if real_motion:
            return {
                "root_dx": deltas[-1]["dx"],
                "root_dy": deltas[-1]["dy"],
                "drift_corrected": False,
                "real_motion": True,
                "root_track": deltas,
                "corrections": []
            }

        return {
            "root_dx": 0,
            "root_dy": 0,
            "drift_corrected": True,
            "real_motion": False,
            "root_track": deltas,
            "corrections": [
                {"dx": -delta["dx"], "dy": -delta["dy"]}
                for delta in deltas
            ]
        }
