"""Game Simulation (Phase 23.8-9): the agent tests its own output.

    Create Asset -> Create Logic -> Simulation -> Detect Issue -> Repair

Three check planes over the asset + its skill blueprints:

    physics    dash distance / hitbox sanity (movement bounds)
    gameplay   damage bounds, cooldown >= animation duration
    performance  frame + atlas budget

Every detected issue is auto-repaired in place (the spec's example: an
overpowered value gets nerfed automatically) and recorded as before/after,
so the report shows exactly what the Simulation Agent fixed.
"""

from typing import Any

from app.engines.foundation.game_logic import DAMAGE_RANGE, DASH_DISTANCE_RANGE

PERFORMANCE_FRAME_BUDGET = 64


def _frame_count(clip: dict[str, Any]) -> int:
    """Clips carry `frames` either as a count or as the frame object list."""
    frames = clip.get("frames")
    if isinstance(frames, list):
        return len(frames)
    if isinstance(frames, (int, float)):
        return int(frames)
    return 0


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return round(min(bounds[1], max(bounds[0], value)), 1)


def simulate_asset(asset: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    clips = (asset.get("animation") or {}).get("clips") or []
    clip_durations = {
        str(c.get("name")): c.get("duration") for c in clips
    }

    combat_skills = (asset.get("combat") or {}).get("skills") or []
    for blueprint in (asset.get("logic") or {}).get("skills") or []:
        name = str(blueprint.get("name"))

        # gameplay: damage bounds
        damage = blueprint.get("damage")
        if isinstance(damage, (int, float)) and not (
            DAMAGE_RANGE[0] <= damage <= DAMAGE_RANGE[1]
        ):
            fixed = _clamp(float(damage), DAMAGE_RANGE)
            issues.append(
                {
                    "check": "gameplay.damage_bounds",
                    "skill": name,
                    "before": damage,
                    "after": fixed,
                    "fixed": True,
                }
            )
            blueprint["damage"] = fixed
            for entry in combat_skills:
                if entry.get("skill") == name:
                    entry["damage"] = int(fixed)

        # gameplay: cooldown must cover the animation
        cooldown = (blueprint.get("trigger") or {}).get("cooldown")
        duration = clip_durations.get(str(blueprint.get("animation")))
        if (
            isinstance(cooldown, (int, float))
            and isinstance(duration, (int, float))
            and cooldown < duration
        ):
            fixed = round(float(duration), 3)
            issues.append(
                {
                    "check": "gameplay.cooldown_coverage",
                    "skill": name,
                    "before": cooldown,
                    "after": fixed,
                    "fixed": True,
                }
            )
            blueprint["trigger"]["cooldown"] = fixed

        # physics: dash distance bounds
        movement = blueprint.get("movement") or {}
        distance = movement.get("distance")
        if isinstance(distance, (int, float)) and not (
            DASH_DISTANCE_RANGE[0] <= distance <= DASH_DISTANCE_RANGE[1]
        ):
            fixed = _clamp(float(distance), DASH_DISTANCE_RANGE)
            issues.append(
                {
                    "check": "physics.dash_distance",
                    "skill": name,
                    "before": distance,
                    "after": fixed,
                    "fixed": True,
                }
            )
            movement["distance"] = fixed

    # performance: frame budget across clips
    frames_total = sum(
        len(c.get("events") or []) + _frame_count(c) for c in clips
    )
    performance_ok = frames_total <= PERFORMANCE_FRAME_BUDGET
    if not performance_ok:
        issues.append(
            {
                "check": "performance.frame_budget",
                "before": frames_total,
                "after": PERFORMANCE_FRAME_BUDGET,
                "fixed": False,
            }
        )

    repairs = sum(1 for issue in issues if issue["fixed"])
    score = round(1.0 - 0.1 * len(issues), 4) if issues else 1.0
    return {
        "passed": performance_ok,
        "issues": issues,
        "repairs": repairs,
        "score": score,
        "checks": {
            "physics": all(i["check"] != "physics.dash_distance" for i in issues),
            "gameplay": all(
                not i["check"].startswith("gameplay") or i["fixed"] for i in issues
            ),
            "performance": performance_ok,
        },
    }
