"""Animation Knowledge Library (Phase 19.11).

Every known action carries semantics + difficulty, so the Motion Agent
resolves "what animation to build" from the intent instead of keyword
guessing scattered across the pipeline:

    Attack  -> Sword Slash / Punch / Magic
    Movement-> Run / Jump / Dodge
"""

from typing import Any

ANIMATION_LIBRARY: dict[str, dict[str, Any]] = {
    "attack": {
        "name": "sword_attack",
        "semantic": "close melee attack",
        "difficulty": "medium",
        "weapon": "sword",
        "body": "upper",
        "speed": "fast",
    },
    "run": {
        "name": "run",
        "semantic": "locomotion cycle",
        "difficulty": "easy",
        "weapon": None,
        "body": "full",
        "speed": "medium",
    },
    "jump": {
        "name": "jump",
        "semantic": "vertical displacement",
        "difficulty": "medium",
        "weapon": None,
        "body": "full",
        "speed": "fast",
    },
    "idle": {
        "name": "idle",
        "semantic": "breathing loop",
        "difficulty": "easy",
        "weapon": None,
        "body": "full",
        "speed": "slow",
    },
}


def resolve_action(requested: list[str]) -> str:
    """First requested action that the library knows; idle as fallback."""
    for action in requested:
        if action in ANIMATION_LIBRARY:
            return action
    return "idle"


def describe(action: str) -> dict[str, Any] | None:
    return ANIMATION_LIBRARY.get(action)
