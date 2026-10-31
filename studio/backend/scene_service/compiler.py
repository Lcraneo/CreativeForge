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

PVE_ENEMY_ASSETS = {
    "slime": {"asset_id": "ast64960", "name": "森林史莱姆"},
    "boss": {"asset_id": "ast60574", "name": "冰霜巨龙"},
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


def validate_pve(level: dict, difficulty: str) -> dict:
    """Validate the first PVE slice: a connected combat lane with one boss."""

    issues: list[str] = []
    platforms = level.get("platforms") or []
    enemies = level.get("enemies") or []
    encounters = level.get("encounters") or []
    enemy_ids = {str(enemy.get("id")) for enemy in enemies}
    if len(platforms) < 1:
        issues.append("战斗路线缺少地面")
    if not _supports(level, level.get("spawnX", -1)):
        issues.append("出生点没有落点")
    if not enemies:
        issues.append("没有配置敌人")
    if not any(enemy.get("kind") == "boss" for enemy in enemies):
        issues.append("缺少 Boss")
    if not encounters:
        issues.append("缺少遭遇战序列")
    for encounter in encounters:
        if encounter.get("trigger_x", 0) >= encounter.get("lock_x", 0):
            issues.append("遭遇战触发点越过了封锁点")
        missing = set(encounter.get("enemy_ids") or []) - enemy_ids
        if missing:
            issues.append("遭遇战引用了不存在的敌人")
    if encounters and encounters[-1].get("kind") != "boss":
        issues.append("最后一个遭遇战必须是 Boss")
    for enemy in enemies:
        if not _supports(level, enemy.get("x", -1)):
            issues.append("{} 没有落点".format(enemy.get("name") or enemy.get("id")))
        if enemy.get("max_hp", 0) <= 0:
            issues.append("{} 生命值无效".format(enemy.get("name") or enemy.get("id")))
    if difficulty not in DIFFICULTIES:
        issues.append("难度无效")
    return {
        "ok": not issues,
        "issues": issues,
        "max_gap": 0,
        "max_rise": 0,
    }


def _select_pve_profile(
    prompt: str, role: str, enemy_pool: list[dict] | None
) -> dict:
    fallback = PVE_ENEMY_ASSETS["slime" if role == "minion" else "boss"]
    candidates = [
        item
        for item in (enemy_pool or [])
        if item.get("role") == role
        and item.get("status") == "ready"
        and item.get("asset_id")
    ]
    if not candidates:
        return fallback
    lowered = prompt.lower()
    keywords = {
        "fast": ("快速", "迅捷", "轻巧", "fast", "swift"),
        "ranged": ("远程", "射击", "法术", "ranged", "shoot"),
        "flying": ("飞行", "翼", "龙", "flying", "wing", "dragon"),
        "armored": ("重甲", "盔甲", "机械", "armored", "armor"),
        "ice": ("冰", "霜", "雪", "ice", "frost"),
        "fire": ("火", "熔岩", "fire", "lava"),
        "toxic": ("毒", "酸", "toxic", "acid"),
        "beast": ("兽", "狼", "虫", "史莱姆", "beast", "wolf", "slime"),
        "undead": ("亡灵", "骷髅", "幽魂", "undead", "skeleton", "ghost"),
        "construct": ("机械", "魔像", "构装", "construct", "golem"),
    }

    def score(profile: dict) -> int:
        text = "{} {} {}".format(
            profile.get("name") or "",
            profile.get("prompt") or "",
            " ".join(profile.get("tags") or []),
        ).lower()
        value = 12 if profile.get("name") and str(profile["name"]).lower() in lowered else 0
        value += sum(3 if tag in text else 0 for tag in profile.get("tags") or [])
        value += sum(
            2
            for tag, words in keywords.items()
            if tag in (profile.get("tags") or [])
            and any(word in lowered for word in words)
        )
        element = profile.get("element")
        value += 2 if element and element in lowered else 0
        return value

    best = max(candidates, key=score)
    if score(best) <= 0 and not any(item.get("builtin") for item in candidates):
        return fallback
    return best


def compile_pve(
    intent: dict,
    seed: int,
    prompt: str = "",
    enemy_pool: list[dict] | None = None,
) -> dict:
    """Compile a lightweight side-scrolling combat lane without collectibles."""

    difficulty = intent["difficulty"]
    base_slimes = {"short": 2, "medium": 3, "long": 5}[intent["length"]]
    slime_count = max(1, base_slimes + {"easy": -1, "normal": 0, "hard": 1}[difficulty])
    width = 2200 + slime_count * 520
    ground_y = GROUND_Y
    platforms = [
        {
            "x": 0,
            "y": ground_y,
            "width": width,
            "height": 72,
            "kind": "ground",
        }
    ]

    minion_profile = _select_pve_profile(prompt, "minion", enemy_pool)
    boss_profile = _select_pve_profile(prompt, "boss", enemy_pool)
    minion_stats = minion_profile.get("stats") or {
        "max_hp": {"easy": 2, "normal": 3, "hard": 4}[difficulty],
        "speed": {"easy": 58, "normal": 72, "hard": 88}[difficulty],
        "damage": 1,
        "attack_interval": 2.4,
        "display_height": 92,
    }
    boss_stats = boss_profile.get("stats") or {
        "max_hp": {"easy": 18, "normal": 24, "hard": 32}[difficulty],
        "speed": 42,
        "damage": 2,
        "attack_interval": 1.35,
        "display_height": 224,
    }
    enemies = []
    boss_x = width - 420
    room1_lock = min(1380, boss_x - 1300)
    room2_start = room1_lock + 180
    room2_lock = boss_x - 640
    half = max(1, (slime_count + 1) // 2)
    rooms = [
        (620, room1_lock, list(range(half))),
        (room2_start, room2_lock, list(range(half, slime_count))),
    ]
    room_encounters = []
    for room_index, (room_start, room_lock, indexes) in enumerate(rooms, start=1):
        if not indexes:
            continue
        enemy_ids = []
        lane_start = room_start + 180
        lane_end = max(lane_start, room_lock - 240)
        for offset, enemy_index in enumerate(indexes):
            ratio = (offset + 1) / (len(indexes) + 1)
            x = round(lane_start + (lane_end - lane_start) * ratio)
            enemy_id = "slime_{}".format(enemy_index + 1)
            enemy_ids.append(enemy_id)
            enemies.append(
                {
                    "id": enemy_id,
                    "profile_id": minion_profile.get("id"),
                    "asset_id": minion_profile.get("asset_id")
                    or PVE_ENEMY_ASSETS["slime"]["asset_id"],
                    "name": minion_profile.get("name")
                    or PVE_ENEMY_ASSETS["slime"]["name"],
                    "kind": "slime",
                    "x": x,
                    "y": ground_y,
                    "behavior": minion_profile.get("behavior") or "chaser",
                    "element": minion_profile.get("element") or "physical",
                    "projectile_color": minion_profile.get("projectile_color")
                    or "#e8d49d",
                    "tags": minion_profile.get("tags") or [],
                    **minion_stats,
                }
            )
        room_encounters.append(
            {
                "id": "encounter_{}".format(room_index),
                "title": "战斗区域 {}".format(room_index),
                "kind": "combat",
                "trigger_x": room_start,
                "lock_x": room_lock,
                "enemy_ids": enemy_ids,
            }
        )

    enemies.append(
        {
            "id": "boss_1",
            "profile_id": boss_profile.get("id"),
            "asset_id": boss_profile.get("asset_id")
            or PVE_ENEMY_ASSETS["boss"]["asset_id"],
            "name": boss_profile.get("name") or PVE_ENEMY_ASSETS["boss"]["name"],
            "kind": "boss",
            "x": boss_x,
            "y": ground_y,
            "behavior": boss_profile.get("behavior") or "guardian",
            "element": boss_profile.get("element") or "ice",
            "projectile_color": boss_profile.get("projectile_color") or "#8feaff",
            "tags": boss_profile.get("tags") or [],
            **boss_stats,
        }
    )
    room_encounters.append(
        {
            "id": "encounter_boss",
            "title": "守关战 · {}".format(
                boss_profile.get("name") or PVE_ENEMY_ASSETS["boss"]["name"]
            ),
            "kind": "boss",
            "trigger_x": boss_x - 520,
            "lock_x": boss_x - 105,
            "enemy_ids": ["boss_1"],
        }
    )
    return {
        "seed": str(seed),
        "width": width,
        "groundY": ground_y,
        "spawnX": 120,
        "goalX": width - 420,
        "platforms": platforms,
        "enemies": enemies,
        "encounters": room_encounters,
    }
