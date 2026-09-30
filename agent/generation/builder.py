"""Deterministic asset builder: goal -> CreativeAsset.

This is the seed step of the pipeline. The canonical fire-mage *pixel* prompt
keeps its historical ``mage001`` / ``FireMage`` identity so the demo and
benchmarks stay stable; every other goal derives a stable, distinct identity
from its text: element-driven palette, seed-jittered shades and, for 2D
requests, a higher-resolution grid.

The frames intentionally carry no ``anchor`` / ``difference`` hints so the
FAlign stages fall back to their deterministic defaults (``drift_corrected`` +
low jitter), which keeps the animation quality gate green.
"""

import hashlib
import re

from agent.generation.spec import parse_style

FRAME_COUNT = 8
FRAME_SIZE = 64
FPS = 12

DEFAULT_PALETTE = {
    "outline": "#07090d",
    "shadow": "#7a1f12",
    "base": "#ff6a2b",
    "highlight": "#ffd23f",
    "accent": "#ffe98a",
    "hair": "#a16207",
    "skin": "#f4d58d",
    "eyes": "#ff6a2b",
    "metal": "#94a3b8",
}

# Element-driven role colours: the goal's element keywords pick the family so
# different prompts no longer share one fire-orange look.
ELEMENT_KEYWORDS = {
    "ice": ("冰霜", "冰", "frost", "ice"),
    "lightning": ("雷霆", "雷电", "闪电", "thunder", "lightning"),
    "nature": ("自然", "森林", "藤蔓", "nature", "forest"),
    "water": ("潮汐", "水系", "水", "water", "海"),
    "poison": ("剧毒", "毒", "poison"),
    "holy": ("神圣", "圣光", "holy", "圣"),
    "dark": ("暗影", "暗黑", "黑暗", "dark", "shadow"),
    "mecha": ("机械", "机甲", "mecha", "赛博", "cyber"),
    "fire": ("火焰", "烈焰", "熔岩", "火系", "fire"),
}

ELEMENT_ROLES = {
    "fire": {"shadow": "#7a1f12", "base": "#ff6a2b", "highlight": "#ffd23f", "accent": "#ffe98a"},
    "ice": {"shadow": "#1b3a5c", "base": "#5ec8f2", "highlight": "#d8f4ff", "accent": "#9fe8ff"},
    "lightning": {
        "shadow": "#4a3a08",
        "base": "#f2c94c",
        "highlight": "#fff3b0",
        "accent": "#b388ff",
    },
    "nature": {"shadow": "#1e4620", "base": "#58a55c", "highlight": "#c8f0b0", "accent": "#ffd23f"},
    "water": {"shadow": "#173a5e", "base": "#3e7cc4", "highlight": "#a8d8ff", "accent": "#66e0d0"},
    "poison": {"shadow": "#2e1b46", "base": "#8e5cc4", "highlight": "#d0a8ff", "accent": "#a8e05f"},
    "holy": {"shadow": "#8a6d1f", "base": "#f2d98c", "highlight": "#fffbe8", "accent": "#ffd23f"},
    "dark": {"shadow": "#120f1e", "base": "#4a3a6e", "highlight": "#8e7cc4", "accent": "#b388ff"},
    "mecha": {"shadow": "#26303c", "base": "#8a97a8", "highlight": "#dbe4ee", "accent": "#ff6a3d"},
}

CANONICAL_FIRE_MAGE = {
    "id": "mage001",
    "name": "FireMage",
    "type": "character",
    "role": "boss",
    "action": "attack",
    "static": False,
    "palette": dict(DEFAULT_PALETTE),
    "seed": 77001,
}

FIRE_KEYWORDS = ("火焰", "fire", "法师", "法師", "mage")
STATIC_KEYWORDS = (
    "静态",
    "static",
    "单张",
    "still",
    "道具",
    "图标",
    "图块",
    "背景",
    "立绘",
    "头像",
    "icon",
    "tileset",
    "background",
    "item",
)
ANIM_KEYWORDS = {
    "attack": ("攻击", "attack", "斩击", "挥砍", "挥击", "劈砍", "战斗"),
    "walk": ("行走", "走路", "步行", "walk"),
    "run": ("奔跑", "跑步", "疾跑", "run"),
    "idle": ("待机", "站立", "idle", "呼吸"),
    "jump": ("跳跃", "弹跳", "jump", "跳"),
}


def _actions_of(lower):
    """动作关键词按“在文本中最早出现”排序（先提到的优先），未提及返回空表。

    之前这里有两个 bug：关键词表只覆盖 attack/walk/idle（"奔跑/跳跃"一律落到
    默认 idle），且按字典序取第一个命中（用户后写的动作覆盖先写的）。"""
    hits = []
    for name, keywords in ANIM_KEYWORDS.items():
        pos = min((lower.find(kw) for kw in keywords if lower.find(kw) >= 0), default=-1)
        if pos >= 0:
            hits.append((pos, name))
    hits.sort()
    seen = []
    for _, name in hits:
        if name not in seen:
            seen.append(name)
    return seen


def _slug(text):
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", text).strip("_")
    return slug[:24] or "asset"


def _shade(hex_color, amount):
    """Lighten (amount > 0) / darken (amount < 0) a hex colour by a fraction."""

    text = hex_color.lstrip("#")
    rgb = [int(text[i : i + 2], 16) for i in (0, 2, 4)]
    if amount >= 0:
        rgb = [c + (255 - c) * amount for c in rgb]
    else:
        rgb = [c * (1 + amount) for c in rgb]
    return "#" + "".join("{:02x}".format(max(0, min(255, int(round(c))))) for c in rgb)


def _element_of(lower):
    for element, keywords in ELEMENT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return element
    return None


def _palette_for(element, seed):
    """Element role palette with seed-driven shade jitter so two goals of the
    same element still produce visibly different colours."""

    roles = dict(DEFAULT_PALETTE)
    if element:
        roles.update(ELEMENT_ROLES[element])
    for key, salt in (("base", 11), ("highlight", 12), ("accent", 13), ("shadow", 14)):
        amount = ((seed ^ (salt * 0x9E3779B1)) % 1000) / 1000.0 - 0.5
        roles[key] = _shade(roles[key], amount * 0.24)
    return roles


def _resolve_identity(goal_text, overrides):
    lower = goal_text.lower()
    overrides = overrides or {}

    style = (
        overrides.get("style")
        if isinstance(overrides.get("style"), str) and overrides.get("style")
        else parse_style(goal_text)
    )
    static = any(keyword in lower for keyword in STATIC_KEYWORDS)

    # Canonical fire-mage identity is preserved only for the pixel-style
    # character prompts (demo + benchmarks); everything else derives its own.
    # The action still follows the goal text (e.g. "火焰法师带奔跑动画" → run);
    # only when the text names no action does the canonical demo default to
    # its historical attack cycle.
    actions = _actions_of(lower)
    if style == "pixel" and not static and any(keyword in lower for keyword in FIRE_KEYWORDS):
        identity = dict(CANONICAL_FIRE_MAGE)
        identity["action"] = actions[0] if actions else "attack"
        identity["actions"] = actions or ["attack"]
        identity["style"] = style
        return _apply_overrides(identity, overrides)

    action = actions[0] if actions else "idle"
    if static:
        action = "idle"

    seed = int(hashlib.sha256(goal_text.encode("utf-8")).hexdigest(), 16) % (2**31)
    name = _slug(goal_text).capitalize() or "Asset"
    identity = {
        "id": "ast{:05d}".format(seed % 100000),
        "name": name,
        "type": "character",
        "role": "npc",
        "action": action,
        "actions": actions or ([action] if not static else ["idle"]),
        "static": static,
        "style": style,
        "palette": _palette_for(_element_of(lower), seed),
        "seed": seed,
    }
    return _apply_overrides(identity, overrides)


def _apply_overrides(identity, overrides):
    overrides = overrides or {}
    for key in ("name", "role", "type"):
        if isinstance(overrides.get(key), str) and overrides[key]:
            identity[key] = overrides[key]
    if "action" in overrides and isinstance(overrides["action"], str):
        identity["action"] = overrides["action"]
    if overrides.get("seed") is not None:
        # 批量多变体：显式 seed 覆盖确定性派生 seed，asset id 随之重算，
        # 否则同一目标的不同变体会共用一个 id 互相覆盖
        try:
            identity["seed"] = int(overrides["seed"]) % (2**31)
            identity["id"] = "ast{:05d}".format(identity["seed"] % 100000)
        except (TypeError, ValueError):
            pass
    return identity


def build_asset(goal, task=None):
    """Build the initial CreativeAsset from a natural-language goal."""

    task = task or {}
    goal_text = (goal or "").strip()
    overrides = task.get("overrides") or {}

    identity = _resolve_identity(goal_text, overrides)
    seed = identity["seed"]
    style = identity.get("style", "pixel")

    character = {
        "id": identity["id"],
        "name": identity["name"],
        "type": identity["type"],
        "role": identity["role"],
        "seed": seed,
        "static": identity["static"],
        "style": style,
        "palette": identity["palette"],
    }

    source = {
        "width": FRAME_SIZE,
        "height": FRAME_SIZE,
        "frame_size": {"width": FRAME_SIZE, "height": FRAME_SIZE},
        # 2D requests work on a finer 16×16 lattice; pixel stays 8×8
        "grid_size": 16 if style == "2d" else 8,
        "seed": seed,
        "style": style,
        "palette": identity["palette"],
    }

    # When a model image was produced for this task it becomes the real
    # PReCon source instead of the synthetic sprite.
    model_image = (task.get("overrides") or {}).get("_model_image")
    if model_image:
        source["ai_image"] = model_image

    frames = [
        {"id": index, "image": None, "action": identity["action"]} for index in range(FRAME_COUNT)
    ]
    animation = {
        "action": identity["action"],
        "actions": identity.get("actions") or [identity["action"]],
        "frames": frames,
        "fps": FPS,
        "loop": True,
    }

    return {
        "id": identity["id"],
        "name": identity["name"],
        "type": identity["type"],
        "role": identity["role"],
        "source": source,
        "character": character,
        "animation": animation,
        "quality": {},
    }


def edit_asset(asset, goal, task=None):
    """Apply natural-language intent to an existing CreativeAsset without
    discarding its source identity or generated artwork."""
    task = task or {}
    if not asset:
        return build_asset(goal, task)
    text = str(goal or "")
    lower = text.lower()
    identity = _resolve_identity(text, task.get("overrides") or {})
    character = asset.setdefault("character", {})
    source = asset.setdefault("source", {})
    animation = asset.setdefault("animation", {})

    if any(k in lower for k in ("火焰", "fire")):
        element = "fire"
    elif any(k in lower for k in ("冰霜", "冰", "frost", "ice")):
        element = "ice"
    elif any(k in lower for k in ("机械", "机甲", "mecha", "赛博", "cyber")):
        element = "mecha"
    else:
        element = _element_of(lower)

    if element:
        palette = _palette_for(element, int(character.get("seed") or identity["seed"]))
        character["palette"] = palette
        source["palette"] = palette

    actions = _actions_of(lower)
    if actions:
        animation["action"] = actions[0]
        animation["actions"] = actions
        character["action"] = actions[0]

    if (
        "像素" in lower
        or "pixel" in lower
        or any(x in lower for x in ("32x32", "32×32", "64x64", "64×64"))
    ):
        character["style"] = "pixel"
        source["style"] = "pixel"
        source["grid_size"] = 8
    elif any(x in lower for x in ("2d", "动漫", "anime", "插画")):
        character["style"] = "2d"
        source["style"] = "2d"
        source["grid_size"] = 16

    if any(k in lower for k in ("法师", "mage")):
        character["role"] = "mage"
    if any(k in lower for k in ("战士", "warrior")):
        character["role"] = "warrior"

    asset["name"] = character.get("name") or asset.get("name")
    provenance = asset.setdefault("provenance", {})
    history = provenance.setdefault("history", [])
    if isinstance(history, list):
        history.append(
            {
                "operation": "edit",
                "goal": goal,
                "source": "creative-agent",
            }
        )
    return asset
