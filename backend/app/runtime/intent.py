"""Intent Analyzer (Phase 16.1 / 18.4 / 22.1).

User goal -> Asset Specification. The Planner plans against this, never
against raw text:

    {
      "type": "game_character_creation",
      "change": "style",            # Phase 22: what kind of edit is wanted
      "engine": "cocos",
      "style": "cyberpunk",
      "actions": ["attack"],
      "requirements": ["character", "weapon", "animation", "combat"]
    }

Phase 22 Goal Analyzer: a modification goal is further classified into a
change type (style / weapon / motion / full) so the Dynamic Planner can
pick a minimal agent chain instead of always running the full pipeline.
"""

from typing import Any

CREATE_KEYWORDS = ("创建", "生成", "做一个", "制作")
MODIFY_KEYWORDS = ("修改", "换成", "换一", "换把", "增加", "加一", "加把", "升级", "改造", "替换", "给")

STYLE_KEYWORDS = (
    ("cyberpunk", ("赛博", "机械", "cyber")),
    ("pixel", ("像素", "pixel")),
    ("anime", ("动漫", "二次元", "anime")),
)

ACTION_KEYWORDS = (
    ("attack", ("攻击", "挥剑", "斩", "attack", "slash")),
    ("run", ("跑", "移动", "run")),
    ("jump", ("跳", "jump")),
)

ENGINE_KEYWORDS = (("unity", "unity"), ("cocos", "cocos"), ("godot", "godot"))

REQUIREMENT_KEYWORDS = (
    ("weapon", ("剑", "刀", "枪", "weapon", "sword", "战士", "warrior")),
    ("armor", ("甲", "盔", "机甲", "armor", "mecha", "机械")),
    ("effect", ("火", "焰", "光", "雷", "effect", "fire", "magic")),
    ("combat", ("战斗", "攻击", "技能", "combat", "skill", "hitbox")),
)

# Phase 22/23 change classification
STYLE_CHANGE_WORDS = ("颜色", "配色", "风格", "样式", "外观", "染色", "改色")
WEAPON_CHANGE_WORDS = ("剑", "刀", "枪", "武器", "装备")
SKILL_CHANGE_WORDS = ("技能", "skill")
MOTION_CHANGE_WORDS = ("动画", "动作", "招式")


def detect_change(goal: str) -> str:
    """Classify a modification goal: style / weapon / skill / motion / full."""
    if any(k in goal for k in STYLE_CHANGE_WORDS):
        return "style"
    if any(k in goal for k in WEAPON_CHANGE_WORDS):
        return "weapon"
    if any(k in goal for k in SKILL_CHANGE_WORDS):
        return "skill"
    if any(k in goal for k in MOTION_CHANGE_WORDS):
        return "motion"
    return "full"


class IntentAnalyzer:
    name = "intent_analyzer"

    def analyze(self, goal: str) -> dict[str, Any]:
        lowered = (goal or "").lower()

        is_modify = any(k in goal for k in MODIFY_KEYWORDS) and not any(
            k in goal for k in CREATE_KEYWORDS
        )
        style = next(
            (name for name, keys in STYLE_KEYWORDS if any(k in lowered for k in keys)),
            "anime",
        )
        actions = [
            name for name, keys in ACTION_KEYWORDS if any(k in lowered for k in keys)
        ] or ["idle"]
        engine = next(
            (name for name, keys in ENGINE_KEYWORDS if any(k in lowered for k in keys)),
            None,
        )
        requirements = ["character"] + [
            name for name, keys in REQUIREMENT_KEYWORDS if any(k in lowered for k in keys)
        ]
        return {
            "type": "character_modification" if is_modify else "game_character_creation",
            "change": detect_change(goal) if is_modify else None,
            "engine": engine,
            "style": style,
            "actions": actions,
            "requirements": requirements,
        }
