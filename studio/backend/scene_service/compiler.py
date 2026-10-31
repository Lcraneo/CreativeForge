"""Turn a semantic scene intent into a deterministic, validated parkour level."""

from __future__ import annotations

import random
import re
from typing import Any

WORLD_HEIGHT = 420
GROUND_Y = 348
PLAYER_HALF_W = 22

DIFFICULTIES = ("easy", "normal", "hard")
LENGTHS = ("short", "medium", "long")
FEATURES = {
    "gaps",
    "rising_platforms",
    "floating_platforms",
    "long_jumps",
    "ice_theme",
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PALETTES = {
    "castle": {
        "skyTop": "#18213d",
        "skyBottom": "#7c8fb5",
        "ground": "#c9d9e8",
        "floating": "#9eb5c8",
        "accent": "#79d6ff",
    },
    "snow": {
        "skyTop": "#233b58",
        "skyBottom": "#b9d5e8",
        "ground": "#e8eff4",
        "floating": "#c7dceb",
        "accent": "#79d6ff",
    },
    "forest": {
        "skyTop": "#6f95a5",
        "skyBottom": "#dce8cf",
        "ground": "#7d9665",
        "floating": "#a5b889",
        "accent": "#e8c76d",
    },
    "lava": {
        "skyTop": "#241b2a",
        "skyBottom": "#7c3d38",
        "ground": "#553d3f",
        "floating": "#81514b",
        "accent": "#ff9a52",
    },
    "desert": {
        "skyTop": "#5c8eaa",
        "skyBottom": "#e8cf9f",
        "ground": "#b78d59",
        "floating": "#cba978",
        "accent": "#ffd46d",
    },
    "city": {
        "skyTop": "#24344d",
        "skyBottom": "#8493a8",
        "ground": "#596878",
        "floating": "#77889a",
        "accent": "#70e0d0",
    },
}


def _text(value: Any, limit: int, fallback: str) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:limit]


def _environment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("snow", "ice", "winter", "雪", "冰", "冬")):
        return "snow"
    if any(word in lowered for word in ("lava", "volcano", "fire", "熔岩", "火山", "烈焰")):
        return "lava"
    if any(word in lowered for word in ("forest", "jungle", "森林", "丛林")):
        return "forest"
    if any(word in lowered for word in ("desert", "sand", "沙漠", "沙丘")):
        return "desert"
    if any(word in lowered for word in ("city", "street", "cityscape", "城市", "街道")):
        return "city"
    return "castle"


def normalize_intent(raw: Any, prompt: str, difficulty: str = "normal") -> dict:
    """Validate model output and fill only the fields needed by the compiler."""

    data = raw if isinstance(raw, dict) else {}
    requested_difficulty = str(difficulty or data.get("difficulty") or "normal").lower()
    if requested_difficulty not in DIFFICULTIES:
        requested_difficulty = "normal"
    length = str(data.get("length") or "medium").lower()
    if length not in LENGTHS:
        length = "medium"

    fallback_environment = _environment(prompt)
    environment = _text(data.get("environment"), 40, fallback_environment).lower()
    if environment not in _PALETTES:
        environment = fallback_environment

    raw_features = data.get("features") if isinstance(data.get("features"), list) else []
    features = [item for item in raw_features if isinstance(item, str) and item in FEATURES]
    if not features:
        features = ["gaps", "rising_platforms"]
    if any(word in prompt.lower() for word in ("浮空", "漂浮", "floating", "island", "岛")):
        if "floating_platforms" not in features:
            features.append("floating_platforms")
    if any(word in prompt.lower() for word in ("长跳", "远跳", "long jump", "大跳")):
        if "long_jumps" not in features:
            features.append("long_jumps")
    if environment == "snow" and "ice_theme" not in features:
        features.append("ice_theme")

    fallback_palette = _PALETTES[environment]
    raw_palette = data.get("palette") if isinstance(data.get("palette"), dict) else {}
    palette = {
        key: (
            str(raw_palette.get(key))
            if _HEX_COLOR.match(str(raw_palette.get(key, "")))
            else fallback_palette[key]
        )
        for key in ("skyTop", "skyBottom", "ground", "floating", "accent")
    }
    return {
        "title": _text(data.get("title"), 40, prompt[:24] or "未命名关卡"),
        "summary": _text(data.get("mood"), 140, prompt[:140] or "由提示词构建的横版跑酷场景"),
        "environment": environment,
        "difficulty": requested_difficulty,
        "length": length,
        "features": features[:8],
        "palette": palette,
    }


def _gap_range(difficulty: str) -> tuple[int, int]:
    return {
        "easy": (78, 112),
        "normal": (92, 142),
        "hard": (108, 170),
    }[difficulty]


def _make_segment(
    rng: random.Random,
    cursor: int,
    current_y: int,
    intent: dict,
) -> tuple[dict, int, int]:
    difficulty = intent["difficulty"]
    min_gap, max_gap = _gap_range(difficulty)
    features = set(intent["features"])
    choices = ["gap", "step_up", "step_down"]
    weights = [3.0, 2.0, 1.0]
    if "floating_platforms" in features:
        choices.append("floating")
        weights.append(2.6)
    if "long_jumps" in features:
        choices.append("long_gap")
        weights.append(1.8)
    kind = rng.choices(choices, weights=weights, k=1)[0]

    max_rise = {"easy": 58, "normal": 72, "hard": 82}[difficulty]
    gap = rng.randint(min_gap, max_gap)
    width = rng.randint(360, 520)
    next_y = current_y
    platform_kind = "ground"

    if kind == "step_up":
        next_y = max(220, current_y - rng.randint(42, max_rise))
    elif kind == "step_down":
        next_y = min(GROUND_Y, current_y + rng.randint(36, 92))
    elif kind == "floating":
        next_y = max(220, current_y - rng.randint(28, max_rise))
        width = rng.randint(190, 280)
        platform_kind = "floating"
    elif kind == "long_gap":
        gap = max_gap
        width = rng.randint(300, 380)
    if next_y < 320:
        platform_kind = "floating"

    platform = {
        "x": cursor + gap,
        "y": next_y,
        "width": width,
        "height": 72 if platform_kind == "ground" else 18,
        "kind": platform_kind,
    }
    return platform, gap, platform["x"] + width


def _supports(level: dict, x: float) -> list[dict]:
    return [
        platform
        for platform in level["platforms"]
        if platform["x"] - PLAYER_HALF_W
        <= x
        <= platform["x"] + platform["width"] + PLAYER_HALF_W
    ]


def validate_parkour(level: dict, difficulty: str) -> dict:
    """Conservative geometric reachability check against the current jump tuning."""

    issues: list[str] = []
    platforms = level.get("platforms") or []
    if len(platforms) < 2:
        issues.append("平台数量不足")
    if not _supports(level, level.get("spawnX", -1)):
        issues.append("出生点没有落点")
    if not _supports(level, level.get("goalX", -1)):
        issues.append("终点没有落点")

    max_gap = {"easy": 130, "normal": 165, "hard": 198}[difficulty]
    max_rise = {"easy": 72, "normal": 88, "hard": 98}[difficulty]
    measured_gap = 0.0
    measured_rise = 0.0
    for platform in platforms:
        if platform["x"] < 0 or platform["y"] < 0:
            issues.append("平台坐标越界")
        if platform["width"] <= 0 or platform["height"] <= 0:
            issues.append("平台尺寸无效")

    edges: dict[int, list[int]] = {index: [] for index in range(len(platforms))}
    for left_index, left in enumerate(platforms):
        for right_index in range(left_index + 1, len(platforms)):
            right = platforms[right_index]
            if right["x"] <= left["x"]:
                continue
            gap = max(0.0, right["x"] - (left["x"] + left["width"]))
            rise = left["y"] - right["y"]
            measured_gap = max(measured_gap, gap)
            measured_rise = max(measured_rise, rise)
            if gap <= max_gap and rise <= max_rise:
                edges[left_index].append(right_index)

    spawn_index = next(
        (
            index
            for index, platform in enumerate(platforms)
            if platform["x"] <= level["spawnX"] <= platform["x"] + platform["width"]
        ),
        None,
    )
    goal_indices = {
        index
        for index, platform in enumerate(platforms)
        if platform["x"] <= level["goalX"] <= platform["x"] + platform["width"]
    }
    reachable: set[int] = set()
    if spawn_index is not None:
        stack = [spawn_index]
        while stack:
            index = stack.pop()
            if index in reachable:
                continue
            reachable.add(index)
            stack.extend(edges[index])
    if not reachable.intersection(goal_indices):
        issues.append("出生点到终点不连通")

    return {
        "ok": not issues,
        "issues": issues,
        "max_gap": round(measured_gap, 1),
        "max_rise": round(measured_rise, 1),
    }


def compile_parkour(intent: dict, seed: int) -> dict:
    rng = random.Random(seed)
    segment_count = {"short": 5, "medium": 7, "long": 9}[intent["length"]]
    platforms = [
        {
            "x": 0,
            "y": GROUND_Y,
            "width": 500,
            "height": 72,
            "kind": "ground",
        }
    ]
    coins: list[dict] = []
    cursor = 500
    current_y = GROUND_Y
    coin_number = 1

    for _ in range(segment_count):
        platform, gap, cursor = _make_segment(rng, cursor, current_y, intent)
        previous = platforms[-1]
        if gap >= 120:
            coins.append(
                {
                    "id": f"c{coin_number}",
                    "x": round(previous["x"] + previous["width"] + gap * 0.5),
                    "y": min(previous["y"], platform["y"]) - 62,
                }
            )
            coin_number += 1
        platforms.append(platform)
        current_y = platform["y"]
        count = 2 if platform["width"] >= 280 else 1
        for offset in range(count):
            coins.append(
                {
                    "id": f"c{coin_number}",
                    "x": round(platform["x"] + platform["width"] * (0.36 + 0.3 * offset)),
                    "y": platform["y"] - 38,
                }
            )
            coin_number += 1

    finish, _gap, _finish_end = _make_segment(
        random.Random(seed ^ 0xA5A5A5A5), cursor, current_y, intent
    )
    finish["width"] = 520
    finish["kind"] = "ground" if finish["y"] >= 320 else "floating"
    finish["height"] = 72 if finish["kind"] == "ground" else 18
    platforms.append(finish)
    goal_x = finish["x"] + finish["width"] - 100
    level = {
        "seed": str(seed),
        "width": finish["x"] + finish["width"],
        "groundY": GROUND_Y,
        "spawnX": 120,
        "goalX": goal_x,
        "platforms": platforms,
        "coins": coins,
    }
    return level
