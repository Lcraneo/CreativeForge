"""Segmentation engine (Phase 13.6): Vision knows it is a sword, SAM2
knows which pixels belong to the sword.

    Vision -> Object Prompt -> SAM2 -> Mask

MVP: deterministic pseudo-SAM2 that derives a stable region (bbox + mask
path + confidence) from the image id, so downstream extraction has real
geometry to work with. Replace `predict` with the SAM2 model call later.
"""

from pathlib import PurePosixPath
from typing import Any

from app.utils import stable_hash

CANVAS = 512


def _region(seed: int) -> list[int]:
    """Map a hash to a stable bbox inside the 512x512 canvas."""
    x = 40 + seed % 120
    y = 30 + (seed >> 8) % 90
    w = 140 + (seed >> 16) % 180
    h = 180 + (seed >> 24) % 200
    return [x, y, min(x + w, CANVAS - 10), min(y + h, CANVAS - 10)]


class SamProcessor:
    """Also exposed under the phase-doc name `Segmenter`."""

    name = "sam2"

    async def segment(self, image: str, object_name: str) -> dict[str, Any]:
        seed = stable_hash(f"{image}:{object_name}")
        stem = PurePosixPath(image).stem
        return {
            "image": image,
            "object": object_name,
            "mask": f"{stem}_{object_name}_mask.png",
            "bbox": _region(seed),
            "confidence": 0.86 + (seed % 13) / 100.0,
        }

    async def predict(self, image: str, object_name: str) -> dict[str, Any]:
        return await self.segment(image, object_name)


Segmenter = SamProcessor
