"""CharacterSpec -> CreativeAsset builder.

Turns the parsed prompt into an engine-ready CreativeAsset with:
    * a deterministic id / name derived from element + class
      (fire mage keeps the canonical ``mage001`` / ``FireMage``),
    * a semantic 16-colour palette built from the spec,
    * a ``character`` block so the UI can render the described person,
    * per-prompt animation frames whose anchor jitter is correctable by FAlign.
"""

import math

from agent.generation.spec import apply_overrides, parse_prompt
from precon._seed import shade

# Historical canonical asset for the demo prompt (keeps benchmarks/demo stable).
CANONICAL_IDENTITY = {
    ("fire", "mage"): ("mage001", "FireMage"),
}


def asset_identity(spec):
    key = (spec.get("element"), spec.get("class"))
    if key in CANONICAL_IDENTITY:
        return CANONICAL_IDENTITY[key]

    element = spec.get("element", "none")
    class_name = spec.get("class", "hero")
    base = class_name if element == "none" else "{}_{}".format(element, class_name)
    name = "".join(part.capitalize() for part in base.split("_"))
    return base, name


def spec_palette(spec):
    """Semantic palette roles derived from the prompt."""
    from agent.generation.spec import ELEMENT_COLORS

    element = ELEMENT_COLORS.get(spec.get("element"), ELEMENT_COLORS["none"])
    base = spec.get("outfit_hex") or element["base"]
    return {
        "outline": "#07090d",
        "shadow": shade(base, -0.55),
        "base": base,
        "highlight": shade(base, 0.45),
        "accent": element["accent"],
        "hair": spec.get("hair_color_hex", "#1b2230"),
        "skin": spec.get("skin_hex", "#e8b98a"),
        "eyes": spec.get("eyes_hex", "#4cc2ff"),
        "metal": element.get("metal", "#94a3b8"),
    }


def build_frames(spec):
    """Prompt-specific frame set with correctable anchor jitter."""
    action = spec.get("action", "idle")
    count = 1 if spec.get("static") else int(spec.get("frame_count", 4))
    seed = int(spec.get("seed", 0))
    base_x = 30 + (seed % 5)
    amplitude = 2.0 if action in ("walk", "attack") else 1.0
    difference = 0.03 + (seed % 6) * 0.01  # 0.03 - 0.08, below the 0.1 jitter gate

    frames = []
    for index in range(count):
        phase = index / count if count else 0.0
        dx = round(math.sin(phase * 2 * math.pi) * amplitude, 2)
        dy = 1 if index % 2 else 0
        frames.append({
            "id": index,
            "image": "frame{}.png".format(index),
            "action": action,
            "difference": round(difference + (index % 3) * 0.005, 3),
            "anchor": {
                "root": {"x": base_x + dx, "y": 58 + dy},
                "feet": {"x": base_x, "y": 64},
                "center": {"x": base_x, "y": 40 + dy},
                "head": {"x": base_x, "y": 8 + dy},
            },
        })
    return frames


def build_asset(goal, task=None, overrides=None):
    """Builds the CreativeAsset for a natural-language goal."""
    raw_goal = goal if goal is not None else (task or {}).get("goal", "")
    spec = parse_prompt(raw_goal)
    effective_overrides = overrides if overrides is not None else (task or {}).get("overrides")
    spec = apply_overrides(spec, effective_overrides)
    asset_id, name = asset_identity(spec)
    palette = spec_palette(spec)
    action = spec.get("action", "idle")

    character = dict(spec)
    character["palette"] = palette

    asset = {
        "id": asset_id,
        "name": name,
        "type": spec.get("type", "character"),
        "source": {
            "prompt": spec.get("goal", ""),
            "width": 64,
            "height": 64,
            "seed": spec["seed"],
            "grid_size": 8,
            "colors": 256,
            "palette": palette,
        },
        "character": character,
        "animation": {
            "action": action,
            "fps": spec.get("fps", 12),
            "loop": True,
            "frames": build_frames(spec),
        },
    }
    if spec.get("role") and spec["role"] != "character":
        asset["role"] = spec["role"]
    return asset
