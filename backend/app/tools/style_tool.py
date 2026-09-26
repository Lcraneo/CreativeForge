"""Style Tool (Phase 22.1): style-only edit on the latest version.

The Dynamic Planner's minimal chain for a style change:

    find_character -> modify_style -> quality_check

The previous version's full asset (layers / animation / combat / engine
payload) is reused; only the palette changes and the version graph grows.
No regeneration, no identity drift — `next_image_for` keeps the encoder's
identity stem so the DNA vector stays inside the same character.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.engines.character_dna.service import next_image_for
from app.tools.base import BaseTool

COLOR_WORDS = (
    ("red", ("红", "red"), "#e23b3b"),
    ("blue", ("蓝", "blue"), "#2f7fe0"),
    ("gold", ("金", "gold", "黄"), "#e0b53f"),
    ("purple", ("紫", "purple"), "#8e5bd9"),
    ("green", ("绿", "green"), "#3fae6a"),
    ("white", ("白", "white"), "#e8e8ee"),
    ("black", ("黑", "black"), "#1a1a20"),
)


def detect_color(goal: str) -> dict[str, str]:
    lowered = (goal or "").lower()
    for name, keys, hex_value in COLOR_WORDS:
        if any(k in lowered for k in keys):
            return {"name": name, "hex": hex_value}
    return {"name": "accent", "hex": "#ff7a45"}


class StyleTool(BaseTool):
    name = "modify_style"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        base = context.get("character")
        previous = context.get("previous_asset")
        if not base or not previous:
            return {
                "status": "skipped",
                "reason": "style edit needs a known character memory",
            }

        asset = deepcopy(previous)
        target = detect_color(context["goal"])

        palette = ((asset.get("pixel") or {}).get("palette") or {}).get("colors")
        if isinstance(palette, list) and palette:
            palette[-1] = target["hex"]
        else:
            asset.setdefault("pixel", {})["palette"] = {"colors": [target["hex"]]}
            palette = asset["pixel"]["palette"]["colors"]
        identity = asset.setdefault("identity", {})
        if isinstance(identity.get("color"), list) and identity["color"]:
            identity["color"][-1] = target["hex"]

        version = services.dna.versions.next_version(base["character_id"])
        image = next_image_for(base.get("image_stem") or base["character_id"], version)
        asset["content"]["image"] = image
        identity["prompt"] = context["goal"]
        asset["version"] = {
            "created": datetime.now(timezone.utc).isoformat(),
            "label": version,
        }

        changes = {
            "change_type": "style_change",
            "target": target["name"],
            "hex": target["hex"],
        }
        action = (asset.get("animation") or {}).get("action") or "idle"
        dna = await services.dna.new_version(base, asset, changes, action=action)
        asset["dna"] = {
            **(asset.get("dna") or {}),
            "character_id": dna["character_id"],
            "identity": dna["identity"],
            "version": dna["versions"][-1],
            "versions": dna["versions"],
            "identity_similarity": dna.get("identity_similarity"),
        }

        context["asset"] = asset
        context["dna"] = dna
        context["version"] = version
        context.setdefault("decisions", []).append(
            f"style-only edit: palette -> {target['name']}, animation/combat reused from v"
            f"{len(dna['versions']) - 1}"
        )
        return {
            "version": version,
            "image": image,
            "palette": palette[:6],
            "changed": ["palette"],
            "identity_similarity": dna.get("identity_similarity"),
        }
