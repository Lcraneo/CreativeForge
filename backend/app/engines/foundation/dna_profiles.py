"""Character DNA profile (Phase 19.4): identity beyond one vector.

The embedding answers "is this the same character"; the six-layer profile
answers "who is this character" in a form both agents and users can read:

    Character DNA
    ├── Appearance DNA   metal / color weights
    ├── Style DNA        art style
    ├── Structure DNA    body proportions
    ├── Equipment DNA    weapon / armor
    ├── Motion DNA       action traits
    └── Combat DNA       combat style
"""

from typing import Any

from app.engines.foundation.animation_library import ANIMATION_LIBRARY


def build_dna_profile(asset: dict[str, Any], action: str = "idle") -> dict[str, Any]:
    identity = asset.get("identity") or {}
    prompt = str(identity.get("prompt") or "")
    layers = (asset.get("content") or {}).get("layers") or []
    palette = ((asset.get("pixel") or {}).get("palette") or {}).get("colors") or []
    body = (identity.get("body") or {}) if isinstance(identity.get("body"), dict) else {}
    combat = asset.get("combat") or {}

    lowered = prompt.lower()
    appearance = {
        "metal": 0.8 if any(k in lowered for k in ("机械", "机甲", "robot", "mech")) else 0.2,
        "blue": 0.7 if any(k in lowered for k in ("蓝", "blue")) else 0.3,
    }

    equipment = {
        "weapon": "weapon" in [layer.get("type") for layer in layers],
        "armor": "armor" in [layer.get("name") for layer in layers]
        or "armor" in [layer.get("type") for layer in layers],
    }

    motion_lib = ANIMATION_LIBRARY.get(action) or {}
    hitboxes = combat.get("hitboxes") or []
    combat_dna = {
        "style": "melee" if equipment["weapon"] else "unarmed",
        "aggression": round(min(1.0, 0.4 + 0.1 * len(hitboxes)), 2),
    }

    return {
        "appearance": appearance,
        "style": {"name": (asset.get("style") or {}).get("name") or "unknown"},
        "structure": {
            "height_ratio": body.get("height_ratio", 1.0),
            "head_ratio": body.get("head_ratio", 0.18),
        },
        "equipment": equipment,
        "motion": {
            "primary_action": action,
            "semantic": motion_lib.get("semantic"),
            "speed": motion_lib.get("speed"),
        },
        "combat": combat_dna,
        "palette": palette[:8],
    }
