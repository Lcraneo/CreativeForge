"""Build the image-generation prompt sent to a model API."""

import re

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

# C① 提示词整备：goal 里混入的工程指令（「并导入Unity」等）会一起送进
# 文生图模型，污染画面语义——引擎归属是结构化字段，不属于画布。
_ENGINE_CLAUSE_RE = re.compile(
    r"[，,；;、]?\s*(?:并)?\s*导入\s*(?:到|至|进)?\s*"
    r"(?:unity|cocos|godot|unreal|ue\d?|游戏引擎)\s*(?:项目|引擎|工程)?\s*",
    re.IGNORECASE,
)


def _strip_engine_clauses(text):
    """剥掉目标文本里的引擎导入子句（导入 Unity/Cocos/Godot 及变体）。"""

    return _ENGINE_CLAUSE_RE.sub(" ", str(text or "")).strip(" ，,；;、")


# C② 短词扩写：超短目标（如「法师」「骑士」）缺少构图与呈现方向，
# 补一组中性描述（不指定风格/配色，交由 style tail 与模型默认）。
_BARE_EXPANSION_ZH = "全身立绘，居中构图，造型特征鲜明，服装与配饰细节丰富"
_BARE_EXPANSION_EN = (
    "full-body character illustration, centered composition, "
    "distinctive silhouette, rich costume detail"
)
_BARE_THRESHOLD = 8

# 角色原画是三视图的正面基准：最终 image prompt 必须锁定「完整全身」构图。
# 用户原始描述里可能带「侧视站立 / 正侧面 / 背面 / 回头看」等会破坏正面
# 参考的构图词，先移除再追加统一约束，避免同一句里出现互相冲突的视角。
_CHARACTER_FRAMING_ZH = (
    "单人全身角色标准设定图，正面或轻微三分之四侧身，角色从头到脚完整入画；"
    "头部、双手、双腿和双脚完整可见，不被画面裁切；"
    "双脚完整露出，身体比例自然，四肢无遮挡；"
    "画面居中，人物上下左右留出适当边距；"
    "纯白背景，无文字、无边框、无场景、无其他人物；"
    "服装和身体轮廓完整清晰。"
)
_CHARACTER_FRAMING_EN = (
    "single full-body character reference sheet, front view or a slight three-quarter turn, "
    "character framed head to toe; head, both hands, both legs and both feet fully visible "
    "and not cropped; both feet fully shown, natural proportions, limbs unobstructed; "
    "centered composition with margin on all sides; pure white background, no text, "
    "no border, no scenery, no other characters; costume and body silhouette fully clear."
)

_CONFLICT_VIEW_RE = re.compile(
    r"(?:正侧视站立姿势|侧视站立姿势|正侧视站立|侧视站立|正侧面|侧面站立姿势|侧面站立|"
    r"侧身站立|侧视|侧身|回头看|回头|背影|背面|"
    r"side[-\s]?view|back[-\s]?view|looking\s+back|from\s+behind|facing\s+away)",
    re.IGNORECASE,
)


def _strip_conflicting_view_words(text):
    """移除会与「正面 / 三分之四」冲突的构图词。"""

    return _CONFLICT_VIEW_RE.sub(" ", str(text or "")).strip(" ，,；;、")


def _is_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def build_image_prompt(goal, overrides=None, enhanced_prompt=None, style=None):
    """Compose a style-aware image prompt.

    Prefers an enhanced brief from the chat provider, falls back to the raw
    goal, and appends a style tail **in the same language** as the base text.
    Never forces "pixel" when the user did not ask for it. Engine-import
    clauses are stripped and ultra-short goals get a composition expansion
    so bare inputs like「法师」still render with usable framing.
    """

    if enhanced_prompt:
        base = enhanced_prompt
    elif goal:
        base = goal
    else:
        base = "a game character"

    stripped = _strip_engine_clauses(base)
    if stripped:
        base = stripped
    if len(base.strip()) < _BARE_THRESHOLD:
        subject = base.strip().rstrip("，,、") or ("游戏角色" if _is_chinese(base) else "a game character")
        expansion = _BARE_EXPANSION_ZH if _is_chinese(base) else _BARE_EXPANSION_EN
        base = "{}, {}".format(subject, expansion)

    base = _strip_conflicting_view_words(base)
    if not base:
        base = "游戏角色" if _is_chinese(goal) else "a game character"

    style_key = style or (overrides or {}).get("style") or "auto"
    if _is_chinese(base):
        tail = STYLE_PROMPT_TAILS_ZH.get(style_key, AUTO_TAIL_ZH)
        framing = _CHARACTER_FRAMING_ZH
    else:
        tail = STYLE_PROMPT_TAILS.get(style_key, AUTO_TAIL)
        framing = _CHARACTER_FRAMING_EN
    return "{}, {}, {}".format(base, framing, tail)
