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

# Fixed three-stage campaign. Each arena uses a slanted top-down plane; x is
# horizontal, y is depth and z is reserved for the runtime jump height.
PVE_STAGE_COUNTS = (4, 6, 1)
PVE_ARENA_WIDTH = 1400
PVE_ARENA_DEPTH = 760
PVE_BEHAVIORS = ("chaser", "shooter", "charger", "guardian")
PVE_REMOVED_KEYS = (
    "arena_segments",
    "hazards",
    "covers",
    "encounters",
    "platforms",
    "coins",
)

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


def validate_pve(campaign: dict, difficulty: str) -> dict:
    """Validate the three-stage 2.5D arena campaign."""

    issues: list[str] = []
    stages = campaign.get("stages") or []
    if campaign.get("schema_version") != 2:
        issues.append("PVE 战役必须使用 schema_version 2")
    if not campaign.get("seed"):
        issues.append("PVE 战役缺少 seed")
    if len(stages) != 3:
        issues.append("PVE 战役必须恰好包含三个关卡")

    for key in PVE_REMOVED_KEYS:
        if key in campaign:
            issues.append("PVE 战役不再生成 {}".format(key))

    expected = (("stage_1", "minion"), ("stage_2", "minion"), ("stage_3", "boss"))
    projectile_budget = 0
    for index, (stage_id, kind) in enumerate(expected):
        if index >= len(stages):
            break
        stage = stages[index] or {}
        label = "第 {} 关".format(index + 1)
        if stage.get("id") != stage_id:
            issues.append("{} 的 ID 必须为 {}".format(label, stage_id))
        if stage.get("kind") != kind:
            issues.append("{} 的类型必须为 {}".format(label, kind))
        for key in PVE_REMOVED_KEYS:
            if key in stage:
                issues.append("{} 不再生成 {}".format(label, key))
        arena = stage.get("arena") or {}
        width = arena.get("width", 0)
        depth = arena.get("depth", 0)
        if not 400 <= width <= 4000 or not 300 <= depth <= 2000:
            issues.append("{} 的竞技场尺寸无效".format(label))
        spawn_x, spawn_y = arena.get("spawn_x", -1), arena.get("spawn_y", -1)
        if not (0 <= spawn_x <= width and 0 <= spawn_y <= depth):
            issues.append("{} 的出生点越界".format(label))
        enemies = stage.get("enemies") or []
        if kind == "boss":
            if len(enemies) != 1:
                issues.append("第三关必须有且只有一个 Boss")
            elif enemies[0].get("kind") != "boss":
                issues.append("第三关的敌人必须是 Boss")
        else:
            if not enemies:
                issues.append("{} 没有配置敌人".format(label))
            if any(enemy.get("kind") == "boss" for enemy in enemies):
                issues.append("{} 不能出现 Boss".format(label))
        ids: set[str] = set()
        stage_budget = 0
        for enemy in enemies:
            enemy_id = str(enemy.get("id") or "")
            if not enemy_id or enemy_id in ids:
                issues.append("{} 存在缺失或重复的敌人 ID".format(label))
            ids.add(enemy_id)
            if not enemy.get("asset_id") or not enemy.get("name"):
                issues.append("{} 缺少敌人素材或名称".format(label))
            if enemy.get("behavior") not in PVE_BEHAVIORS:
                issues.append("{} 敌人行为无效".format(label))
            x, y = enemy.get("x", -1), enemy.get("y", -1)
            if not (40 <= x <= max(40, width - 40) and 40 <= y <= max(40, depth - 40)):
                issues.append("{} 敌人越出竞技场".format(label))
            if enemy.get("max_hp", 0) <= 0:
                issues.append("{} 敌人生命值无效".format(label))
            if enemy.get("speed", 0) < 0:
                issues.append("{} 敌人移动速度无效".format(label))
            if enemy.get("damage", 0) <= 0:
                issues.append("{} 敌人伤害无效".format(label))
            if enemy.get("attack_interval", 0) <= 0:
                issues.append("{} 敌人攻击间隔无效".format(label))
            if enemy.get("display_height", 0) <= 0:
                issues.append("{} 敌人显示尺寸无效".format(label))
            stage_budget += max(
                1, round(4 / max(0.5, float(enemy.get("attack_interval", 2))))
            )
        projectile_budget = max(projectile_budget, stage_budget)

    if difficulty not in DIFFICULTIES:
        issues.append("难度无效")
    duration_factor = {"easy": 3.0, "normal": 2.6, "hard": 1.8}.get(difficulty, 2.6)
    total_hp = sum(
        max(0, float(enemy.get("max_hp", 0)))
        for stage in stages
        for enemy in (stage.get("enemies") or [])
    )
    estimated_duration = round(total_hp * duration_factor + len(stages) * 4, 1)
    recommendations = []
    if estimated_duration < 90:
        recommendations.append("预计战斗偏短，建议提高敌人生命")
    elif estimated_duration > 160:
        recommendations.append("预计战斗偏长，建议降低敌人生命")
    if projectile_budget > 20:
        recommendations.append("同屏投射物预算过高，建议延长攻击间隔")
    return {
        "ok": not issues,
        "issues": issues,
        "max_gap": 0,
        "max_rise": 0,
        "combat_metrics": {
            "estimated_duration_seconds": estimated_duration,
            "projectile_budget": projectile_budget,
            "minimum_telegraph_seconds": 0.45,
            "quality_ok": 90 <= estimated_duration <= 160 and projectile_budget <= 20,
            "recommendations": recommendations,
        },
    }


_PVE_KEYWORDS = {
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


def _profile_score(profile: dict, prompt: str) -> int:
    lowered = prompt.lower()
    text = "{} {} {}".format(
        profile.get("name") or "",
        profile.get("prompt") or "",
        " ".join(profile.get("tags") or []),
    ).lower()
    value = 12 if profile.get("name") and str(profile["name"]).lower() in lowered else 0
    value += sum(3 if tag in text else 0 for tag in profile.get("tags") or [])
    value += sum(
        2
        for tag, words in _PVE_KEYWORDS.items()
        if tag in (profile.get("tags") or [])
        and any(word in lowered for word in words)
    )
    element = profile.get("element")
    value += 2 if element and element in lowered else 0
    return value


def _pve_profiles(prompt: str, role: str, enemy_pool: list[dict] | None) -> list[dict]:
    """Rank ready profiles for one role; the fallback is always available."""

    fallback = PVE_ENEMY_ASSETS["slime" if role == "minion" else "boss"]
    candidates = [
        item
        for item in (enemy_pool or [])
        if item.get("role") == role
        and item.get("status") == "ready"
        and item.get("asset_id")
    ]
    if not candidates:
        return [fallback]
    ranked = sorted(candidates, key=lambda item: _profile_score(item, prompt), reverse=True)
    meaningful = [
        item for item in ranked
        if _profile_score(item, prompt) > 0 or item.get("builtin")
    ]
    return meaningful or [fallback]


def _select_pve_profile(prompt: str, role: str, enemy_pool: list[dict] | None) -> dict:
    return _pve_profiles(prompt, role, enemy_pool)[0]


def _pve_stats(profile: dict, difficulty: str, role: str) -> dict:
    defaults = (
        {
            "max_hp": {"easy": 18, "normal": 24, "hard": 32}[difficulty],
            "speed": 42,
            "damage": 2,
            "attack_interval": 1.35,
            "display_height": 224,
        }
        if role == "boss"
        else {
            "max_hp": {"easy": 2, "normal": 3, "hard": 4}[difficulty],
            "speed": {"easy": 58, "normal": 72, "hard": 88}[difficulty],
            "damage": 1,
            "attack_interval": 2.4,
            "display_height": 92,
        }
    )
    stats = profile.get("stats") or {}
    merged = {key: stats.get(key, value) for key, value in defaults.items()}
    # Builtin profiles store normal-mode defaults; the chosen scene difficulty
    # must still affect their combat values. Custom profiles keep user stats.
    if profile.get("builtin"):
        merged["max_hp"] = defaults["max_hp"]
        if role != "boss":
            merged["speed"] = defaults["speed"]
    return merged


def _pve_positions(rng: random.Random, count: int, width: int, depth: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for index in range(count):
        row = index // 3
        column = index % 3
        x = width * (0.2 + 0.6 * (column + 0.5) / 3) + rng.randint(-40, 40)
        y = depth * (0.32 + row * 0.16) + rng.randint(-24, 24)
        positions.append((round(x), round(y)))
    return positions


def _pve_enemy(
    profile: dict, stats: dict, enemy_id: str, kind: str, x: int, y: int
) -> dict:
    fallback = PVE_ENEMY_ASSETS["slime" if kind == "minion" else "boss"]
    return {
        "id": enemy_id,
        "profile_id": profile.get("id"),
        "asset_id": profile.get("asset_id") or fallback["asset_id"],
        "name": profile.get("name") or fallback["name"],
        "kind": kind,
        "x": x,
        "y": y,
        "behavior": profile.get("behavior") or ("guardian" if kind == "boss" else "chaser"),
        "element": profile.get("element") or ("ice" if kind == "boss" else "physical"),
        "projectile_color": profile.get("projectile_color")
        or ("#8feaff" if kind == "boss" else "#e8d49d"),
        "tags": profile.get("tags") or [],
        **stats,
    }


def compile_pve(
    intent: dict,
    seed: int,
    prompt: str = "",
    enemy_pool: list[dict] | None = None,
) -> dict:
    """Compile the fixed three-stage 2.5D arena campaign."""

    difficulty = intent["difficulty"]
    rng = random.Random(seed)
    width = PVE_ARENA_WIDTH
    depth = PVE_ARENA_DEPTH
    arena = {
        "width": width,
        "depth": depth,
        "spawn_x": round(width * 0.5),
        "spawn_y": round(depth * 0.8),
    }

    minion_candidates = _pve_profiles(prompt, "minion", enemy_pool)
    stage1_profile = minion_candidates[0]
    stage1_key = (stage1_profile.get("id"), stage1_profile.get("asset_id"))
    stage2_profile = next(
        (
            item
            for item in minion_candidates
            if (item.get("id"), item.get("asset_id")) != stage1_key
        ),
        stage1_profile,
    )
    boss_profile = _select_pve_profile(prompt, "boss", enemy_pool)

    stages = []
    for index, (stage_id, kind, title) in enumerate(
        (
            ("stage_1", "minion", "第 1 关 · 前哨清剿"),
            ("stage_2", "minion", "第 2 关 · 纵深围猎"),
            (
                "stage_3",
                "boss",
                "第 3 关 · 守关战 · {}".format(
                    boss_profile.get("name") or PVE_ENEMY_ASSETS["boss"]["name"]
                ),
            ),
        )
    ):
        if kind == "boss":
            stats = _pve_stats(boss_profile, difficulty, "boss")
            enemies = [
                _pve_enemy(
                    boss_profile,
                    stats,
                    "stage_3_boss",
                    "boss",
                    round(width * 0.5),
                    round(depth * 0.42),
                )
            ]
        else:
            profile = stage1_profile if index == 0 else stage2_profile
            stats = _pve_stats(profile, difficulty, "minion")
            enemies = [
                _pve_enemy(profile, stats, "{}_enemy_{}".format(stage_id, slot + 1), "minion", x, y)
                for slot, (x, y) in enumerate(
                    _pve_positions(rng, PVE_STAGE_COUNTS[index], width, depth)
                )
            ]
        stages.append(
            {
                "id": stage_id,
                "title": title,
                "kind": kind,
                "background_url": None,
                "arena": dict(arena),
                "enemies": enemies,
            }
        )
    return {"schema_version": 2, "seed": str(seed), "stages": stages}
