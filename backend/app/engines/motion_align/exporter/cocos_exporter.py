"""Cocos animation exporter (Phase 15.2.11 / 15.4.5).

Builds Cocos-shaped metadata: AnimationClip (sample + spriteFrame track)
and the sprite-sheet .plist. The full project package (textures /
spriteframes / animations / prefab) is assembled by the GImport layer.
"""

from typing import Any


def anchor_to_cocos(anchor: dict[str, Any], frame_size: list[int]) -> dict[str, float]:
    """Pixel anchor -> Cocos normalized anchor (0-1)."""
    w = frame_size[0] or 1
    h = frame_size[1] or 1
    return {
        "anchorX": round(anchor["x"] / w, 3),
        "anchorY": round(anchor["y"] / h, 3),
    }


class CocosAnimationExporter:
    name = "cocos"

    def export_clip(self, clip: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": clip["name"],
            "duration": clip["duration"],
            "sample": clip["fps"],
            "tracks": [
                {
                    "property": "spriteFrame",
                    "keys": [frame["id"] for frame in clip["frames"]],
                }
            ],
            "events": clip.get("events", []),
        }

    def export_plist(self, atlas: dict[str, Any]) -> dict[str, Any]:
        frames = {}
        for sprite in atlas.get("sprites", []):
            frames[sprite["name"]] = {
                "frame": f"{{{sprite['x']},{sprite['y']}}},{{{sprite['w']},{sprite['h']}}}",
                "rotated": False,
                "offset": "{0,0}",
            }
        return {
            "frames": frames,
            "metadata": {
                "texture": atlas.get("texture"),
                "size": f"{{{atlas.get('size', [0, 0])[0]},{atlas.get('size', [0, 0])[1]}}}",
            },
        }
