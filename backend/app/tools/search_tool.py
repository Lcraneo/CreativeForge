"""Character Search Tool (Phase 14.11 Step 1-2 / 22.1).

Planner runs this before generation in modify mode: find the existing
character behind the natural language edit and derive what changed.

Phase 22 Asset Context Retriever: the latest full asset of the found
character is loaded into `context["previous_asset"]`, so short chains
(style-only edit) can carry the previous version forward instead of
regenerating everything.
"""

from typing import Any

from sqlalchemy import select

from app.models import Asset, CharacterVersion
from app.tools.base import BaseTool

EQUIPMENT_WORDS = ("剑", "刀", "枪", "weapon", "sword")
ARMOR_WORDS = ("甲", "盔", "机甲", "armor", "mecha")
STYLE_WORDS = ("风格", "style", "颜色", "配色", "color")


def detect_changes(goal: str) -> dict[str, Any]:
    lowered = (goal or "").lower()
    if any(word in lowered for word in EQUIPMENT_WORDS):
        after = "fire_sword" if any(w in lowered for w in ("火", "焰", "fire")) else "sword"
        return {"change_type": "equipment_change", "before": "sword", "after": after}
    if any(word in lowered for word in ARMOR_WORDS):
        return {"change_type": "armor_change", "before": "armor", "after": "mecha"}
    if any(word in lowered for word in STYLE_WORDS):
        return {"change_type": "style_change", "before": "current", "after": "updated"}
    return {"change_type": "edit", "before": "current", "after": "updated"}


class CharacterSearchTool(BaseTool):
    name = "find_character"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        found = services.dna.search_by_text(context["goal"])
        if not found:
            return {"found": False, "reason": "no matching character memory"}
        context["character"] = found
        context["changes"] = detect_changes(context["goal"])

        db = context.get("db")
        if db is not None:
            latest = (
                await db.execute(
                    select(CharacterVersion)
                    .where(CharacterVersion.character_id == found["character_id"])
                    .order_by(CharacterVersion.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if latest is not None and latest.asset_id:
                row = await db.get(Asset, latest.asset_id)
                if row is not None:
                    context["previous_asset"] = row.metadata_json or {}
        return {"found": True, "id": found["character_id"]}
