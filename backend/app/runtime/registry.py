"""Agent Registry + MCP-style tool schemas (Phase 16.14-15 / 17.13).

Every capability exposes a machine-readable description so the Planner can
do capability matching instead of hard-coding flows:

    {"name": "motion_align", "description": "align animation frames",
     "input": {"character_id", "action"}, "output": {"animation"}}
"""

from typing import Any

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "find_character": {
        "name": "find_character",
        "description": "Search character memory for an existing identity (text or image)",
        "input": {"goal": "str"},
        "output": {"found": "bool", "id": "str?"},
    },
    "modify_style": {
        "name": "modify_style",
        "description": "Style-only edit (Phase 22): recolor palette on the latest version, reuse animation/combat/engine payload",
        "input": {"goal": "str", "previous_asset": "CreativeAsset"},
        "output": {"version": "str", "palette": "list"},
    },
    "create_logic": {
        "name": "create_logic",
        "description": "Generate a CreativeSkill blueprint + engine scripts from the goal (Phase 23)",
        "input": {"goal": "str", "previous_asset": "CreativeAsset"},
        "output": {"skill": "str", "damage": "float", "cooldown": "float"},
    },
    "simulate": {
        "name": "simulate",
        "description": "Playtest the asset logic (physics / gameplay / performance) and auto-repair (Phase 23)",
        "input": {"asset": "CreativeAsset"},
        "output": {"passed": "bool", "repairs": "int", "score": "float"},
    },
    "generate_asset": {
        "name": "generate_asset",
        "description": "Generate character image via the Windup adapter (identity-preserving in modify mode)",
        "input": {"goal": "str", "style": "str"},
        "output": {"image": "str", "style": "str"},
    },
    "structure_asset": {
        "name": "structure_asset",
        "description": "Rebuild the image into editable layers, masks and asset graph (Phase 13)",
        "input": {"asset": "CreativeAsset"},
        "output": {"layers": "list", "segmentation_score": "float"},
    },
    "create_dna": {
        "name": "create_dna",
        "description": "Create or version the character identity vector + DNA record (Phase 14)",
        "input": {"asset": "CreativeAsset"},
        "output": {"character_id": "str", "version": "str"},
    },
    "motion_align": {
        "name": "motion_align",
        "description": "Align AI animation frames, extract sprites, build timeline (Phase 15.1-15.3)",
        "input": {"asset": "CreativeAsset", "action": "str"},
        "output": {"action": "str", "frames": "int", "atlas": "str"},
    },
    "combat": {
        "name": "combat",
        "description": "Bind hitboxes to attack frames and emit the skill definition (Phase 15.5)",
        "input": {"asset": "CreativeAsset"},
        "output": {"skill": "str", "damage": "int"},
    },
    "gimport": {
        "name": "gimport",
        "description": "Export the CreativeAsset to an engine project tree (Phase 15.4)",
        "input": {"asset": "CreativeAsset", "engine": "str"},
        "output": {"engine": "str", "files": "list"},
    },
    "quality_check": {
        "name": "quality_check",
        "description": "Validate structural / dna / motion / runtime quality (Phase 16.17)",
        "input": {"asset": "CreativeAsset"},
        "output": {"passed": "bool", "issues": "list"},
    },
}


def describe_tools() -> list[dict[str, Any]]:
    """The MCP-style `tools` payload the Planner reads."""
    return [
        {
            "name": schema["name"],
            "description": schema["description"],
            "input": schema["input"],
            "output": schema["output"],
        }
        for schema in TOOL_SCHEMAS.values()
    ]
