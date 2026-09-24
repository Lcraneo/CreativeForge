REFERENCE_SIZE = 64.0


class AnimationEvaluator:
    """Writes the Animation Quality Score into CreativeAsset quality.animation."""

    def evaluate(self, anchors, motion_result, temporal_result):
        residual_drift = (
            abs(motion_result.get("root_dx", 0))
            + abs(motion_result.get("root_dy", 0))
        )

        anchor_score = round(
            max(0.0, 1.0 - residual_drift / REFERENCE_SIZE), 4
        )
        motion_score = (
            1.0
            if motion_result.get("drift_corrected")
            else round(max(0.5, 1.0 - residual_drift / REFERENCE_SIZE), 4)
        )
        temporal_score = round(
            max(0.0, 1.0 - temporal_result.get("jitter_score", 0.0)), 4
        )
        overall = round(
            (anchor_score + motion_score + temporal_score) / 3, 4
        )

        return {
            "anchor_score": anchor_score,
            "motion_score": motion_score,
            "temporal_score": temporal_score,
            "overall": overall
        }
