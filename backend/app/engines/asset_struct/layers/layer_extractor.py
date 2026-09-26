"""Layer Extractor (Phase 13.7): Image + Mask -> Alpha-channel PNG layer.

MVP keeps everything metadata level: the extracted layer is a derived path
plus its geometry. Real pixel compositing (mask -> alpha channel) drops in
behind the same signature once Pillow lands.
"""

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any


@dataclass
class AssetLayer:
    name: str
    type: str
    image: str
    mask: str
    bbox: list[float]
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LayerExtractor:
    def extract(self, image: str, segmentation: dict[str, Any]) -> AssetLayer:
        stem = PurePosixPath(image).stem
        name = segmentation["object"]
        return AssetLayer(
            name=name,
            type=name,
            image=f"{stem}_{name}.png",
            mask=segmentation["mask"],
            bbox=list(segmentation["bbox"]),
            confidence=segmentation.get("confidence", 0.0),
        )
