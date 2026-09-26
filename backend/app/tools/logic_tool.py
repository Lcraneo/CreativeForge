"""Game Logic Tool (Phase 23.6): route create_logic to the engine.

Attaches a CreativeSkill blueprint (with engine scripts) to the character,
bumps the version graph and syncs the game-facing combat skill list. The
Knowledge Retriever's facts about this character ride along in the
blueprint so the produced logic is grounded in the asset graph.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.engines.foundation.game_logic import build_skill_blueprint, engine_scripts
from app.tools.base import BaseTool


class GameLogicTool(BaseTool):
    name = "create_logic"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        base = context.get("character")
        previous = context.get("previous_asset")
        if not base or not previous:
            return {
                "status": "skipped",
                "reason": "logic creation needs a known character memory",
            }

        asset = deepcopy(previous)
        character_name = (asset.get("identity") or {}).get("name") or "character"
        blueprint = build_skill_blueprint(context["goal"], character_name)
        blueprint["related_facts"] = (context.get("knowledge") or {}).get("facts") or []
        blueprint["engine"] = engine_scripts(blueprint)

        logic = asset.setdefault("logic", {})
        skills = logic.setdefault("skills", [])
        skills[:] = [s for s in skills if s.get("name") != blueprint["name"]]
        skills.append(blueprint)

        combat_skills = asset.setdefault("combat", {}).setdefault("skills", [])
        combat_skills[:] = [
            s for s in combat_skills if s.get("skill") != blueprint["name"]
        ]
        combat_skills.append(
            {
                "skill": blueprint["name"],
                "animation": blueprint["animation"],
                "damage": blueprint["damage"],
                "element": blueprint.get("element"),
            }
        )

        version = services.dna.versions.next_version(base["character_id"])
        asset["version"] = {
            "created": datetime.now(timezone.utc).isoformat(),
            "label": version,
        }
        identity = asset.setdefault("identity", {})
        identity["prompt"] = context["goal"]
        changes = {
            "change_type": "skill_addition",
            "skill": blueprint["name"],
            "type": blueprint["type"],
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
            f"logic: {blueprint['name']} ({blueprint['type']}) blueprint + engine scripts"
        )
        return {
            "skill": blueprint["name"],
            "type": blueprint["type"],
            "damage": blueprint["damage"],
            "cooldown": blueprint["trigger"]["cooldown"],
            "animation": blueprint["animation"],
            "effect": blueprint["effect"],
            "version": version,
            "identity_similarity": dna.get("identity_similarity"),
        }
