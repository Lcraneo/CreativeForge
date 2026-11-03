ENGINE_KEYWORDS = {
    "unity": ("unity",),
    "cocos": ("cocos", "cocos creator"),
    "godot": ("godot",),
}

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
ANIMATION_KEYWORDS = (
    "动画",
    "animation",
    "待机",
    "idle",
    "攻击",
    "attack",
    "行走",
    "走路",
    "walk",
    "奔跑",
    "跑步",
    "run",
    "跳跃",
    "jump",
    "施法",
    "cast",
    "受击",
    "hit",
)
PIXEL_KEYWORDS = (
    "像素",
    "pixel",
    "pixel art",
    "sprite",
    "精灵图",
    "32x32",
    "32×32",
    "64x64",
    "64×64",
    "16x16",
    "16×16",
    "8-bit",
    "16-bit",
)
STYLE_2D_KEYWORDS = ("2d", "2d 动漫", "动漫", "anime", "插画", "illustration")
MODIFY_KEYWORDS = (
    "改",
    "修改",
    "调整",
    "换成",
    "变成",
    "重做",
    "重新做",
    "再做",
    "加上",
    "增加",
    "删除",
    "replace",
    "change",
    "modify",
    "edit",
    "update",
    "redo",
    "add",
    "remove",
)
IMPORT_PHRASES = ("导入", "import", "接入", "写入项目", "放进项目")


class IntentAnalyzer:
    """Extracts intent without forcing a fixed production pipeline."""

    def analyze(self, goal, has_asset=False):
        text = str(goal or "").strip().lower()

        engine = None
        for engine_name, keywords in ENGINE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                engine = engine_name
                break

        static = any(keyword in text for keyword in STATIC_KEYWORDS)
        needs_animation = any(keyword in text for keyword in ANIMATION_KEYWORDS) and not static
        pixel_requested = any(keyword in text for keyword in PIXEL_KEYWORDS)
        style = (
            "2d"
            if any(keyword in text for keyword in STYLE_2D_KEYWORDS) and not pixel_requested
            else "pixel"
        )
        modification = has_asset and any(keyword in text for keyword in MODIFY_KEYWORDS)
        explicit_import = engine is not None and any(keyword in text for keyword in IMPORT_PHRASES)

        # A bare engine name is treated as an import request as well: users
        # commonly say "做完给 Unity" rather than "导入 Unity".
        if engine is not None:
            explicit_import = True

        return {
            "goal": goal,
            "style": style,
            "asset_type": "character" if not static else "asset",
            "engine": engine,
            "has_asset": has_asset,
            "modification": modification,
            "requires": {
                "generation": not has_asset,
                "pixel_reconstruction": pixel_requested,
                "animation_alignment": needs_animation,
                "engine_import": explicit_import,
            },
            "needs_animation": needs_animation,
            "requested_actions": self._actions(text),
        }

    @staticmethod
    def _actions(text):
        actions = (
            ("attack", ("攻击", "attack", "斩击", "挥砍", "挥击")),
            ("walk", ("行走", "走路", "步行", "walk")),
            ("run", ("奔跑", "跑步", "疾跑", "run")),
            ("idle", ("待机", "站立", "idle")),
            ("jump", ("跳跃", "jump")),
            ("cast", ("施法", "cast")),
            ("hit", ("受击", "hit")),
        )
        hits = []
        for name, keywords in actions:
            positions = [text.find(word) for word in keywords if text.find(word) >= 0]
            if positions:
                hits.append((min(positions), name))
        hits.sort()
        return [name for _, name in hits]
