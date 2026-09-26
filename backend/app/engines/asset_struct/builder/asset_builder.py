"""Asset Struct Builder (Phase 13.9 / 13.10).

Assembles the CreativeAsset additions the AssetStruct engine is responsible
for: mount anchors (auto generated from the body geometry in the MVP),
pixel info (palette + grid) and the segmentation quality score.
"""

from typing import Any

DEFAULT_PALETTE = ["#111111", "#3a3a3a", "#ffaa00", "#00c8ff", "#8a5a2a"]


def build_anchors(body_bbox: list[float]) -> dict[str, list[float]]:
    """Game mount points: root at the feet center, hand / feet offsets."""
    x1, y1, x2, y2 = body_bbox
    cx = round((x1 + x2) / 2, 1)
    return {
        "root": [cx, round(y2, 1)],
        "hand": [round(x2 - (x2 - x1) * 0.1, 1), round(y1 + (y2 - y1) * 0.55, 1)],
        "feet": [cx, round(y2, 1)],
    }


def build_pixel(palette: list[str] | None = None) -> dict[str, Any]:
    return {
        "grid": {"size": 8},
        "palette": {"colors": list(palette or DEFAULT_PALETTE)},
    }


class AssetBuilder:
    def build(
        self,
        asset: dict[str, Any],
        layers: list[dict[str, Any]],
        graph: dict[str, Any],
        segmentation_score: float,
    ) -> dict[str, Any]:
        asset = dict(asset)
        asset["content"] = dict(asset.get("content") or {})
        asset["content"]["layers"] = layers
        asset["content"]["graph"] = graph

        body = next((l for l in layers if l["name"] == "body"), layers[0] if layers else None)
        visual = {"bounding_box": body["bbox"] if body else [0, 0, 0, 0]}
        visual["anchor_point"] = build_anchors(body["bbox"]) if body else build_anchors([0, 0, 1, 1])
        asset["visual"] = visual

        asset["pixel"] = build_pixel((asset.get("style") or {}).get("palette"))

        quality = dict(asset.get("quality") or {})
        quality["segmentation_score"] = round(segmentation_score, 4)
        asset["quality"] = quality
        return asset
