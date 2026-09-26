"""Hitbox / Hurtbox generation (Phase 15.5).

Reuses the AssetStruct layer masks instead of re-detecting:

    Weapon Layer -> Mask -> expand -> Hitbox polygon
    Body Layer   -> Mask          -> Hurtbox polygon

The expansion approximates morphological dilation on the bbox (the weapon
edge is not the real attack range); per-pixel dilation lands with real
mask rasters.
"""

from typing import Any

from app.engines.motion_align.timeline.event import active_window


def bbox_polygon(bbox: list[float], expand: float = 0.0) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    return [
        [round(x1 - expand, 1), round(y1 - expand, 1)],
        [round(x2 + expand, 1), round(y1 - expand, 1)],
        [round(x2 + expand, 1), round(y2 + expand, 1)],
        [round(x1 - expand, 1), round(y2 + expand, 1)],
    ]


class HitboxGenerator:
    name = "hitbox_generator"

    def __init__(self, expand_radius: float = 8.0):
        self.expand_radius = expand_radius

    async def generate(
        self,
        asset: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        frame_count: int = 0,
    ) -> dict[str, Any]:
        layers = (asset.get("content") or {}).get("layers") or []
        weapon = next((l for l in layers if l.get("type") == "weapon"), None)
        body = next((l for l in layers if l.get("name") == "body"), layers[0] if layers else None)

        enable = next((e["frame"] for e in events or [] if e["type"] == "hitbox_enable"), None)
        disable = next((e["frame"] for e in events or [] if e["type"] == "hitbox_disable"), None)
        if enable is None and frame_count:
            enable, disable = active_window(frame_count)

        hitboxes = []
        if weapon is not None:
            hitboxes.append(
                {
                    "name": weapon["name"],
                    "shape": "polygon",
                    "points": bbox_polygon(weapon["bbox"], self.expand_radius),
                    "frames": list(range(enable or 1, (disable or (enable or 1)) + 1)),
                    "damage": 100,
                }
            )
        hurtboxes = []
        if body is not None:
            hurtboxes.append(
                {
                    "name": "body",
                    "type": "normal",
                    "shape": "polygon",
                    "points": bbox_polygon(body["bbox"]),
                }
            )
        return {"hitboxes": hitboxes, "hurtboxes": hurtboxes}
