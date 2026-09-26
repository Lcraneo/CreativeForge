"""Sprite Cropper (Phase 15.2.4): image + bbox -> cropped layer.

MVP keeps crops metadata level (derived path + geometry); the real
`image.crop(bbox)` lands with Pillow behind the same signature.
"""

from pathlib import PurePosixPath
from typing import Any


class SpriteCropper:
    def crop(self, image: str, region: dict[str, Any]) -> dict[str, Any]:
        x1, y1, x2, y2 = region["bbox"]
        stem = PurePosixPath(image).stem
        return {
            "image": image,
            "cropped": f"{stem}_crop.png",
            "bbox": [x1, y1, x2, y2],
            "size": [round(x2 - x1, 1), round(y2 - y1, 1)],
        }
