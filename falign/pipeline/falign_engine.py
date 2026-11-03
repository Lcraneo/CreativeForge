from falign.extraction.frame_extractor import FrameExtractor
from falign.anchor.anchor_detector import AnchorDetector
from falign.phase.phase_alignment import PhaseAligner
from falign.motion.root_motion import RootMotionCorrector
from falign.temporal.temporal_consistency import TemporalAnalyzer
from falign.quality.animation_quality import AnimationEvaluator


class FAlignEngine:
    """Frame Extraction -> Anchor -> Phase -> Root Motion -> Temporal -> Quality."""

    def __init__(self):
        self.extractor = FrameExtractor()
        self.anchor = AnchorDetector()
        self.phase = PhaseAligner()
        self.motion = RootMotionCorrector()
        self.temporal = TemporalAnalyzer()
        self.quality = AnimationEvaluator()

    def process(self, frames):
        normalized_frames = self.extractor.process(frames)

        anchors = self.anchor.detect(normalized_frames)

        phase_result = self.phase.align(
            normalized_frames,
            anchors
        )

        motion_result = self.motion.correct(
            normalized_frames,
            anchors
        )

        temporal_result = self.temporal.analyze(normalized_frames)

        quality = self.quality.evaluate(
            anchors,
            motion_result,
            temporal_result
        )

        return {
            "animation": {
                "frames": normalized_frames,
                "anchor": anchors,
                "phase": phase_result,
                "motion": motion_result
            },
            "quality": {
                "animation": quality
            }
        }
