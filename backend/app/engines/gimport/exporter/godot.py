"""Godot exporter (Phase 18.10): same asset, Godot project tree.

    assets/characters/<name>/
        textures/<name>_atlas.png
        spriteframes/<name>.tres        (SpriteFrames resource)
        animations/<clip>.tres          (Animation resources)
        scenes/<name>.tscn              (Sprite2D + AnimationPlayer + Area2D)
"""

from typing import Any

from app.engines.gimport.exporter.base import EngineExporter


class GodotExporter(EngineExporter):
    name = "godot"

    async def export(self, asset: dict[str, Any]) -> dict[str, Any]:
        name = (asset.get("identity") or {}).get("name") or "character"
        animation = asset.get("animation") or {}
        combat = asset.get("combat") or {}
        clips = animation.get("clips") or []
        if not clips and animation.get("timeline"):
            clips = [animation["timeline"]]

        files: dict[str, Any] = {
            f"textures/{name}_atlas.png": {"type": "Texture2D"},
            f"spriteframes/{name}.tres": {
                "type": "SpriteFrames",
                "animations": [clip["name"] for clip in clips] or ["idle"],
            },
            f"scenes/{name}.tscn": {
                "node": name.capitalize(),
                "components": ["Sprite2D", "AnimationPlayer", "Area2D"],
                "colliders": {
                    "hurtbox": combat.get("hurtboxes", []),
                    "hitbox": combat.get("hitboxes", []),
                },
            },
        }
        for clip in clips:
            files[f"animations/{clip['name']}.tres"] = {
                "type": "Animation",
                "length": clip["duration"],
                "fps": clip["fps"],
                "tracks": ["sprite_frame"],
            }
        return {
            "engine": self.name,
            "character": name,
            "root": f"assets/characters/{name}",
            "files": files,
            "quality": {"manifest_score": 1.0, "runtime_score": 1.0},
        }
