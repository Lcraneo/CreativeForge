"""DNA Tool (Phase 14.11 / 19.4): create DNA for a new character or record
a new version for an existing one, with the six-layer DNA profile and an
identity-similarity assessment (Phase 19.12)."""

from typing import Any

from app.engines.foundation.quality_model import assess_identity
from app.tools.base import BaseTool


def _requested_action(context: dict[str, Any]) -> str:
    actions = ((context.get("intent") or {}).get("actions") or ["idle"])
    return actions[0] if actions else "idle"


class DnaTool(BaseTool):
    name = "create_dna"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        asset = context["asset"]
        base = context.get("character")
        action = _requested_action(context)

        if base:
            changes = context.get("changes") or {"change_type": "edit"}
            dna = await services.dna.new_version(base, asset, changes, action=action)
            # Phase 19.12: consistency assessment between versions.
            old_profile = base.get("profile") or (base.get("identity") or {}).get(
                "dna_profile"
            )
            similarity = assess_identity(
                {"profile": old_profile or {}, "identity": base.get("identity") or {}},
                {"profile": dna.get("profile") or {}, "identity": dna.get("identity") or {}},
            )
            dna["identity_similarity"] = similarity
            asset.setdefault("dna", {})["identity_similarity"] = similarity["similarity"]
        else:
            dna = await services.dna.create(asset, action=action)

        asset["dna"] = {
            **(asset.get("dna") or {}),
            "character_id": dna["character_id"],
            "identity": dna["identity"],
            "version": dna["versions"][-1],
            "versions": dna["versions"],
        }
        context["dna"] = dna
        return {"character_id": dna["character_id"], "version": dna["versions"][-1]}
