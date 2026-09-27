"""Parse a natural-language goal into a structured spec and apply overrides."""

STYLE_KEYWORDS = (
    # "2d" checked first: an explicit 2D request wins over a generic pixel hit
    ("2d", ("2d", "二次元", "动漫", "手绘", "插画", "anime", "cartoon", "扁平", "日式", "立绘")),
    ("pixel", ("像素", "pixel", "8bit", "8-bit", "16bit", "16-bit")),
)


def parse_style(text):
    """Detect the requested art style from the goal text (default: pixel)."""

    lower = (text or "").lower()
    for style, keywords in STYLE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return style
    return "pixel"


def parse_prompt(goal):
    """Turn a free-text goal into a minimal generation spec.

    The spec is consumed by the external chat provider for prompt enhancement
    and by the supervisor when nothing else is configured.
    """

    text = (goal or "").strip()
    engine = None
    lower = text.lower()
    for candidate in ("unity", "cocos", "godot"):
        if candidate in lower:
            engine = candidate
            break
    return {
        "raw": text,
        "type": "character",
        "style": parse_style(text),
        "engine": engine,
        "keywords": [word for word in text.split() if word],
    }


def apply_overrides(spec, overrides):
    """Merge user-supplied overrides onto a parsed spec (non-null wins)."""

    spec = dict(spec or {})
    if isinstance(overrides, dict):
        spec.update({key: value for key, value in overrides.items() if value is not None})
    return spec
