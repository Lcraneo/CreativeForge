"""Combat Agent (Phase 16.10): combat logic only.

Weapon mask -> hitbox -> event binding -> damage. Reads what MotionAlign
produced, never touches generation, and emits the game-facing skill
definition (Phase 15.3.10 skill system).
"""

from typing import Any

from app.runtime.agents.base import BaseAgent

DEFAULT_DAMAGE = 100


class CombatAgent(BaseAgent):
    name = "CombatAgent"
    task = "combat"

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        asset = context["asset"]
        combat = asset.get("combat") or {}
        animation = asset.get("animation") or {}
        action = animation.get("action") or "idle"

        hitboxes = combat.get("hitboxes") or []
        if hitboxes:
            primary = hitboxes[0]
            skill_name = (
                "fire_slash"
                if "fire" in str(primary.get("name", "")).lower() or action == "attack"
                else f"{action}_skill"
            )
            skill = {
                "skill": skill_name,
                "animation": action,
                "damage": primary.get("damage", DEFAULT_DAMAGE),
                "frames": primary.get("frames", []),
                "element": "fire" if "fire" in skill_name else "physical",
            }
            skills = combat.setdefault("skills", [])
            skills[:] = [s for s in skills if s.get("skill") != skill_name]
            skills.append(skill)
            asset["combat"] = combat
            return {"skill": skill_name, "damage": skill["damage"], "hitbox_frames": skill["frames"]}

        return {"skill": None, "damage": 0, "hitbox_frames": []}
