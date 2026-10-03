"""vo_script — 发布片旁白脚本：五段带节奏的叙述片段（纯函数、确定性）。

节奏对齐 timeline_mapper 的节拍表：每段旁白绑定一个叙事窗（beat window），
窗长按说话速率换算成字数上限——文案超限会被截断或回落更短的候选句，
保证任何一段都不会压到下一拍的画面上。

旁白不逐字跟画（那是字幕的事），而是"段起点对齐拍点、窗内说完即可"。
presentation["copy"]["vo"] 可整段覆写（5 元素列表，按 hook/art/pixel/
anim/engine 顺序）。
"""

from __future__ import annotations

# 说话速率（字/秒，含标点停顿的保守值）——超出窗长的句子必然吃掉下一拍
CHARS_PER_SEC = 4.2
# 段首相对拍点的起播提前量（秒），让 voice 先于画面动作一点点落地
LEAD_IN = 0.05

# 五段叙事窗（kind, 起始拍, 结束拍）——拍名与 timeline_mapper.BEATS 对齐
_WINDOW_BEATS = (
    ("hook", "hookIn", "hookOut"),
    ("art", "artIn", "sweep"),
    ("pixel", "morphPixel1", "morphAnim0"),
    ("anim", "animIn", "animOut"),
    ("engine", "morphEngine1", "engineOut"),
)

# 每拍的候选句（由短到长排列）：取能装进窗长的最长候选。
# {name} 用资产显示名替换；均按发布会旁白口吻写。
_TEMPLATES = {
    "hook": ("{name}", "一镜到底"),
    "art": ("AI 原画就绪", "原画就绪"),
    "pixel": ("像素级重建", "像素重建"),
    "anim": ("动作自动展开，一气呵成", "动作展开，一气呵成", "动作就绪"),
    "engine": ("导出进入引擎，发布就绪", "进入引擎，发布就绪", "发布就绪"),
}

# 指令式风格提示（qwen3-tts-instruct-flash 的 instructions 参数）——
# 按拍定风格：能力清单里的"语音风格匹配"落点
STYLE_HINTS = {
    "hook": "轻快清晰的开场播报语气，简短有力",
    "art": "沉稳大气的产品介绍旁白，高端发布会风格",
    "pixel": "沉稳叙述，略带技术感",
    "anim": "充满力量感与速度感的动作描述，语气渐强",
    "engine": "自信收束的结束语调，留有余韵",
}


def _display_name(scene: dict) -> str:
    """scene_mapper 已收敛过的 header 短名，直接复用。"""

    return str((scene.get("copy") or {}).get("name") or "").strip()


def _char_cap(window: float) -> int:
    """窗长 → 字数上限（含标点）。"""

    return max(2, int(window * CHARS_PER_SEC))


def _fit(text: str, cap: int) -> str:
    """把文案装进字数上限：优先去尾部标点，再硬截。"""

    text = (text or "").strip()
    while len(text) > cap and text[-1] in "，。！？、,.!? ":
        text = text[:-1]
    if len(text) > cap:
        text = text[:cap]
    while text and text[-1] in "，、 ":
        text = text[:-1]
    return text if len(text) >= 2 else ""


def build_script(scene: dict, cf: dict | None = None) -> list[dict]:
    """→ 五段旁白：[{kind, text, start, window, cap, style}]。

    cf 提供真实节拍（build_timeline 产物）；缺省时用 timeline 的常拍表，
    保证离线单测可跑。覆写：scene["copy"]["vo"]（列表，按五拍顺序）。
    """

    beats = dict((cf or {}).get("beats") or {})
    if not beats:
        from adapters.onetake.timeline_mapper import BEATS

        beats = dict(BEATS)

    copy = scene.get("copy") or {}
    name = _display_name(scene)
    overrides = copy.get("vo") if isinstance(copy.get("vo"), list) else None

    segments: list[dict] = []
    for kind, beat_start, beat_end in _WINDOW_BEATS:
        start = float(beats.get(beat_start, 0.0))
        end = float(beats.get(beat_end, start + 2.0))
        window = max(0.6, end - start)
        cap = _char_cap(window)
        style = STYLE_HINTS.get(kind, "沉稳的中文旁白")

        if overrides is not None:
            text = _fit(str(overrides[len(segments)]) if len(segments) < len(overrides) else "", cap)
        else:
            text = ""
            # 优先选"不截断就装得下"的最长候选，避免硬切在词中间
            for candidate in _TEMPLATES[kind]:
                candidate = candidate.format(name=name) if "{name}" in candidate else candidate
                if len(candidate) <= cap and len(candidate) > len(text):
                    text = candidate
            if not text:
                for candidate in _TEMPLATES[kind]:
                    fitted = _fit(
                        candidate.format(name=name) if "{name}" in candidate else candidate, cap
                    )
                    if len(fitted) > len(text):
                        text = fitted
        if not text:
            continue
        segments.append(
            {
                "kind": kind,
                "text": text,
                "start": round(start + LEAD_IN, 3),
                "window": round(window, 3),
                "cap": cap,
                "style": style,
            }
        )
    return segments


def apply_polish(base_segments: list[dict], polished_texts: list[str]) -> list[dict]:
    """把 AI 润色文本套回片段结构：装得下字数上限才采用，超限整句不信任、
    回落原文（不做硬截断——截断的润色句比模板更差）。条数不符/全空/
    全部超限都保持 base 不动。
    """

    if not isinstance(polished_texts, list) or len(polished_texts) != len(base_segments):
        return base_segments
    out = []
    changed = 0
    for seg, text in zip(base_segments, polished_texts):
        text = str(text or "").strip()
        if 2 <= len(text) <= seg["cap"]:
            out.append({**seg, "text": text})
            changed += 1
        else:
            out.append(seg)
    return out if changed else base_segments
