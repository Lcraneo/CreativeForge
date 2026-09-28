"""Build the image-generation prompt sent to a configured model API."""

# Per-style tails. NOTE: no "transparent background" here — text-to-image
# models cannot produce real alpha and will silently ignore/blank it; ask for a
# plain solid background instead. Tails are language-matched to the base prompt
# so a Chinese goal gets a Chinese tail (friendlier for DashScope/wanx).
STYLE_PROMPT_TAILS = {
    "pixel": "pixel art game asset, clean 1px lineart, limited palette, plain solid background",
    "2d": "2d anime style illustration, clean cel shading, full body, plain solid background",
    "3d": "3d rendered game character, soft studio lighting, plain solid background",
}
AUTO_TAIL = "clean lineart, high detail, plain solid background"

STYLE_PROMPT_TAILS_ZH = {
    "pixel": "像素风游戏素材，干净的1像素描边，有限调色板，纯色背景",
    "2d": "2D 动漫风插画，干净的赛璐璐上色，全身，纯色背景",
    "3d": "3D 渲染游戏角色，柔和棚拍光，纯色背景",
}
AUTO_TAIL_ZH = "干净线稿，高细节，纯色背景"


def _is_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def build_image_prompt(goal, overrides=None, enhanced_prompt=None, style=None):
    """Compose a style-aware image prompt.

    Prefers an enhanced brief from the chat provider, falls back to the raw
    goal, and appends a style tail **in the same language** as the base text.
    Never forces "pixel" when the user did not ask for it.
    """

    if enhanced_prompt:
        base = enhanced_prompt
    elif goal:
        base = goal
    else:
        base = "a game character"

    style_key = style or (overrides or {}).get("style") or "auto"
    if _is_chinese(base):
        tail = STYLE_PROMPT_TAILS_ZH.get(style_key, AUTO_TAIL_ZH)
    else:
        tail = STYLE_PROMPT_TAILS.get(style_key, AUTO_TAIL)
    return "{}, {}".format(base, tail)
