"""CreativeForge Asset Benchmark Dataset.

Categories mirror the target usage of an AI game asset factory. Every entry
describes one CreativeAsset production goal; the benchmark runs the real
pipeline on each entry and scores the result against a naive baseline.

Deterministic: entries are fixed, engines are deterministic, so benchmark
runs are reproducible.
"""

CATEGORIES = (
    "characters",
    "monsters",
    "npc",
    "weapons",
    "effects",
    "environments",
)

# One entry = one benchmark unit. "source_colors" models the AI image color
# count that PReCon must compress; "frames" / "drift_px" model the raw AI
# animation noise that FAlign must fix.
ENTRIES = [
    {"id": "fire_mage_001", "category": "characters", "type": "character",
     "goal": "创建一个像素RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目",
     "engine": "cocos", "action": "attack", "frames": 4, "drift_px": 3,
     "source_colors": 256},
    {"id": "frost_knight_002", "category": "characters", "type": "character",
     "goal": "生成一个像素冰霜骑士，带行走动画，导入Unity",
     "engine": "unity", "action": "walk", "frames": 6, "drift_px": 3,
     "source_colors": 128},
    {"id": "cave_boss_003", "category": "monsters", "type": "character",
     "goal": "做一个像素洞穴Boss，带攻击动画，导入Unity",
     "engine": "unity", "action": "attack", "frames": 8, "drift_px": 3,
     "source_colors": 256},
    {"id": "forest_wolf_004", "category": "monsters", "type": "character",
     "goal": "生成像素森林狼怪物，带奔跑动画，导入Godot",
     "engine": "godot", "action": "run", "frames": 6, "drift_px": 3,
     "source_colors": 64},
    {"id": "village_smith_005", "category": "npc", "type": "character",
     "goal": "创建一个像素村庄铁匠NPC，带待机动画，导入Cocos项目",
     "engine": "cocos", "action": "idle", "frames": 4, "drift_px": 2,
     "source_colors": 96},
    {"id": "merchant_006", "category": "npc", "type": "character",
     "goal": "生成一个像素商贩NPC，导入Unity",
     "engine": "unity", "action": "idle", "frames": 2, "drift_px": 2,
     "source_colors": 64},
    {"id": "flame_sword_007", "category": "weapons", "type": "item",
     "goal": "生成一把像素火焰剑道具，导入Unity",
     "engine": "unity", "action": None, "frames": 0, "drift_px": 0,
     "source_colors": 32},
    {"id": "thunder_axe_008", "category": "weapons", "type": "item",
     "goal": "做一个像素雷霆战斧图标，导入Cocos项目",
     "engine": "cocos", "action": None, "frames": 0, "drift_px": 0,
     "source_colors": 48},
    {"id": "fire_burst_009", "category": "effects", "type": "effect",
     "goal": "生成像素火焰爆发特效动画，导入Unity",
     "engine": "unity", "action": "burst", "frames": 4, "drift_px": 1,
     "source_colors": 64},
    {"id": "heal_glow_010", "category": "effects", "type": "effect",
     "goal": "做一个像素治疗光效动画，导入Godot",
     "engine": "godot", "action": "glow", "frames": 4, "drift_px": 1,
     "source_colors": 32},
    {"id": "dungeon_wall_011", "category": "environments", "type": "tileset",
     "goal": "生成像素地牢墙壁图块，导入Unity",
     "engine": "unity", "action": None, "frames": 0, "drift_px": 0,
     "source_colors": 64},
    {"id": "magic_forest_012", "category": "environments", "type": "tileset",
     "goal": "创建像素魔法森林背景，导入Cocos项目",
     "engine": "cocos", "action": None, "frames": 0, "drift_px": 0,
     "source_colors": 128},
]


def dataset():
    """The full benchmark dataset, grouped by category."""
    grouped = {category: [] for category in CATEGORIES}
    for entry in ENTRIES:
        grouped[entry["category"]].append(entry)
    return grouped


def animated_entries():
    return [entry for entry in ENTRIES if entry["frames"] > 0]


def static_entries():
    return [entry for entry in ENTRIES if entry["frames"] == 0]


def by_id(entry_id):
    for entry in ENTRIES:
        if entry["id"] == entry_id:
            return dict(entry)
    raise LookupError("unknown dataset entry: {}".format(entry_id))
