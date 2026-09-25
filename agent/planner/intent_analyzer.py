ENGINE_KEYWORDS = {
    "unity": ("unity",),
    "cocos": ("cocos",),
    "godot": ("godot",)
}

STATIC_KEYWORDS = (
    "静态", "static", "单张", "still",
    "道具", "图标", "图块", "背景", "立绘", "头像",
    "icon", "tileset", "background", "item"
)

ANIMATION_KEYWORDS = (
    "动画", "animation", "待机", "idle", "攻击", "attack", "行走", "walk"
)


class IntentAnalyzer:
    """Understands the user goal before planning."""

    def analyze(self, goal):
        text = str(goal).lower()

        engine = "cocos"
        for engine_name, keywords in ENGINE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                engine = engine_name
                break

        requires = {
            "generation": True,
            "pixel_reconstruction": True,
            "animation_alignment": not any(
                keyword in text for keyword in STATIC_KEYWORDS
            ),
            "engine_import": True
        }

        return {
            "goal": goal,
            "style": "pixel",
            "asset_type": "character",
            "engine": engine,
            "requires": requires,
            "needs_animation": any(
                keyword in text for keyword in ANIMATION_KEYWORDS
            )
        }
