"""Unity exporter stub (Phase 15.4.2).

Same asset, multiple engines: Unity shape (AnimatorController + .prefab
YAML skeleton). The real Unity YAML serialization lands later; the
boundary is frozen now so callers never change.
"""

from typing import Any

from app.engines.gimport.exporter.base import EngineExporter


class UnityExporter(EngineExporter):
    name = "unity"

    async def export(self, asset: dict[str, Any]) -> dict[str, Any]:
        name = (asset.get("identity") or {}).get("name") or "character"
        animation = asset.get("animation") or {}
        clips = animation.get("clips") or []
        if not clips and animation.get("timeline"):
            clips = [animation["timeline"]]

        files: dict[str, Any] = {
            f"textures/{name}_atlas.png": {"type": "Sprite"},
            f"prefab/{name}.prefab": {
                "node": name,
                "components": ["SpriteRenderer", "Animator", "PolygonCollider2D"],
            },
            "animator/controller.controller": {
                "states": [clip["name"] for clip in clips]
                or [animation.get("action") or "idle"],
            },
        }
        for clip in clips:
            files[f"animations/{clip['name']}.anim"] = {"type": "AnimationClip"}
        return {
            "engine": self.name,
            "character": name,
            "root": f"Assets/Characters/{name}",
            "files": files,
            "quality": {"manifest_score": 1.0, "runtime_score": 1.0},
        }
