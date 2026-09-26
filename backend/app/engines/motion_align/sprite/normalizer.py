"""Padding Normalizer (Phase 15.2.5) — Anchor Based Padding.

All frames must share one size, but the character must NOT be centered:
centering breaks attacks where the sword swings off-body. Instead the root
anchor is pinned to a fixed slot inside the uniform frame.
"""

from typing import Any


class PaddingNormalizer:
    def __init__(
        self,
        frame_size: tuple[int, int] = (128, 128),
        anchor_slot: tuple[int, int] = (64, 110),
    ):
        self.frame_size = frame_size
        self.anchor_slot = anchor_slot

    def normalize(
        self, cropped: dict[str, Any], anchor: tuple[float, float]
    ) -> dict[str, Any]:
        offset_x = self.anchor_slot[0] - anchor[0]
        offset_y = self.anchor_slot[1] - anchor[1]
        return {
            "name": None,  # filled by the atlas generator
            "source": cropped["cropped"],
            "frame_size": list(self.frame_size),
            "anchor": {"x": self.anchor_slot[0], "y": self.anchor_slot[1]},
            "offset": [round(offset_x, 1), round(offset_y, 1)],
        }
