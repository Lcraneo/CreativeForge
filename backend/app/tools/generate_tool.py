"""Generate Tool (Phase 11.9 -> 12.9 -> 14.11).

Create mode:  prompt -> Windup adapter -> CreativeAsset.
Modify mode:  the character identity comes from the found DNA; only the
              changed part is regenerated on a new version image, keeping
              colour / face / proportions / style untouched.
"""

from datetime import datetime, timezone
from typing import Any

from app.adapters.registry import ensure_adapters
from app.engines.character_dna.service import next_image_for
from app.tools.base import BaseTool


class GenerateTool(BaseTool):
    name = "generate_asset"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        goal = context["goal"]
        base = context.get("character")

        if base:
            # Phase 14 Step 4: identity-preserving modification.
            version = services.dna.versions.next_version(base["character_id"])
            image = next_image_for(base.get("image_stem") or base["character_id"], version)
            identity = dict(base.get("identity") or {})
            asset = {
                "identity": {
                    **identity,
                    "prompt": goal,
                    "character_id": base["character_id"],
                },
                "source": {
                    "provider": "windup",
                    "mode": "identity_preserved",
                    "base_character": base["character_id"],
                },
                "content": {"image": image},
                "style": {"name": identity.get("style") or "anime"},
                "version": {
                    "created": datetime.now(timezone.utc).isoformat(),
                    "label": version,
                },
            }
            context["version"] = version
        else:
            adapter = ensure_adapters().get("windup")
            asset = await adapter.generate({"prompt": goal})
            asset.setdefault("identity", {})["prompt"] = goal

        context["asset"] = asset
        return {
            "image": asset["content"]["image"],
            "style": asset["style"]["name"],
        }
