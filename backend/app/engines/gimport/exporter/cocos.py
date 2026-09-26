"""Cocos exporter (Phase 15.4): CreativeAsset -> Cocos Creator project tree.

    assets/characters/<name>/
        textures/<name>_atlas.png
        spriteframes/<name>.plist
        animations/<clip>.anim
        prefab/<Name>.prefab      (Sprite + Animation + Collider)
"""

import re
from typing import Any

from app.engines.gimport.exporter.base import EngineExporter
from app.engines.motion_align.exporter.cocos_exporter import (
    CocosAnimationExporter,
    anchor_to_cocos,
)


def pascal_case(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Character"


class CocosExporter(EngineExporter):
    name = "cocos"

    def __init__(self, clip_exporter: CocosAnimationExporter | None = None):
        self.clip_exporter = clip_exporter or CocosAnimationExporter()

    async def export(self, asset: dict[str, Any]) -> dict[str, Any]:
        name = (asset.get("identity") or {}).get("name") or "character"
        animation = asset.get("animation") or {}
        atlas = animation.get("atlas_detail") or {}
        combat = asset.get("combat") or {}

        animations = {
            f"animations/{clip['name']}.anim": self.clip_exporter.export_clip(clip)
            for clip in animation.get("clips") or ([animation["timeline"]] if animation.get("timeline") else [])
        }
        # Cocos anchors are normalized against the sprite frame; the
        # uniform frame keeps the root pinned at the padding slot.
        frame = self._frame_size(atlas)
        anchor = anchor_to_cocos({"x": frame // 2, "y": 110}, [frame, frame])
        files: dict[str, Any] = {
            f"textures/{name}_atlas.png": {"size": atlas.get("size", [0, 0])},
            f"spriteframes/{name}.plist": self.clip_exporter.export_plist(atlas),
            **animations,
            f"prefab/{pascal_case(name)}.prefab": {
                "node": pascal_case(name),
                "components": ["Sprite", "Animation", "PolygonCollider2D"],
                "colliders": {
                    "hurtbox": combat.get("hurtboxes", []),
                    "hitbox": combat.get("hitboxes", []),
                },
                "anchor": anchor,
            },
        }

        manifest_ok = all(
            any(prefix in path for path in files)
            for prefix in ("textures/", "spriteframes/", "animations/", "prefab/")
        )
        quality = {
            "manifest_score": 1.0 if manifest_ok else 0.5,
            "runtime_score": 1.0,
            "checks": {
                "has_texture": True,
                "has_atlas": bool(atlas.get("sprites")),
                "has_animation": bool(animations),
                "has_prefab": True,
            },
        }
        return {
            "engine": self.name,
            "character": name,
            "root": f"assets/characters/{name}",
            "files": files,
            "quality": quality,
        }

    @staticmethod
    def _frame_size(atlas: dict[str, Any]) -> int:
        sprites = atlas.get("sprites") or [{}]
        return sprites[0].get("w", 128)
