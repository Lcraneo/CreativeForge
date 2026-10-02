"""scene_mapper — 素材清单 + presentation → 合成文案/场景语义（纯函数）。

文案纪律（onetake SKILL 硬规则）：hook 是一句画面性陈述而非产品介绍；
节拍标签与 build 面板行一一对应（tick 是第二载体）；不引入粒子/彩带类
模板化装饰。presentation.copy 可整体覆写默认文案。
"""

import os

DEFAULT_HOOK = ["AI 生成", "像素重建", "引擎就绪"]
DEFAULT_LINES = ["原画就绪", "PReCon 像素重建", "FAlign 动作就绪", "GImport 导出", "Showcase 渲染"]
DEFAULT_LABELS = {
    "art": ["01", "原画"],
    "pixel": ["02", "PReCon 像素重建"],
    "anim": ["03", "FAlign 动作展开"],
    "engine": ["04", "GImport → Cocos 预览"],
}
DEFAULT_STAC = ["就绪", "发布", "一镜到底"]

TOKENS = {
    "bg": "#f8f8f6",
    "ink": "#161616",
    "grey": "#8f8f8b",
    "green": "#17a05e",
    "red": "#b42323",
    "card": "#ffffff",
    "line": "#e8e8e4",
}

# look 八色令牌 → 合成 CSS 变量映射（paper 与工作台暖纸编辑风同源；
# cf-paper 为骑士原画实测烘焙的暗蓝变体，adapters/onetake/looks/）
LOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "looks")
LOOK_TO_TOKEN = {
    "ground": "bg",
    "card": "card",
    "line": "line",
    "mute": "grey",
    "ink": "ink",
    "accent": "green",
    "accent2": "red",
}
DEFAULT_LOOK = "paper"


def _look_tokens(look_name: str | None) -> dict:
    """按名加载 look 并映射为合成 tokens；look 文件缺失回落 paper 默认。"""

    name = str(look_name or DEFAULT_LOOK)
    path = os.path.join(LOOK_DIR, "{}.json".format(name))
    try:
        import json as _json

        with open(path, "r", encoding="utf-8") as handle:
            colors = (_json.load(handle) or {}).get("color") or {}
        mapped = {
            token: colors[source]
            for source, token in LOOK_TO_TOKEN.items()
            if colors.get(source)
        }
        return {**TOKENS, **mapped} if len(mapped) >= 5 else dict(TOKENS)
    except Exception:  # noqa: BLE001 - look 缺失/损坏回落默认，永不阻塞
        return dict(TOKENS)


def build_scene(material: dict, presentation: dict | None = None) -> dict:
    """→ 合成文案段（CF.copy / CF.tokens / CF.stac）。纯函数、可离线单测。

    look 按 presentation.look 名字选择（默认 paper，与工作台暖纸同源），
    从 adapters/onetake/looks/{name}.json 读取八色并映射为合成 tokens。"""

    presentation = presentation or {}
    override = presentation.get("copy") or {}
    tokens = _look_tokens(presentation.get("look"))
    raw_name = str(material.get("name") or "未命名角色")
    name = _display_name(raw_name)
    prompt = str(material.get("prompt") or "").strip()

    hook = override.get("hook")
    if not hook or not isinstance(hook, list) or not (2 <= len(hook) <= 4):
        hook = _hook_from_prompt(prompt)

    stac = override.get("stac")
    if not stac or not isinstance(stac, list) or len(stac) != 3:
        stac = list(DEFAULT_STAC)

    labels = DEFAULT_LABELS
    if isinstance(override.get("labels"), dict) and override["labels"]:
        labels = {**DEFAULT_LABELS, **override["labels"]}

    return {
        "tokens": tokens,
        "copy": {
            "hook": [str(w)[:14] for w in hook],
            "name": name,
            "headerTag": "CreativeForge Showcase",
            "panelTitle": "CreativeForge Pipeline",
            "lines": list(override.get("lines") or DEFAULT_LINES),
            "labels": labels,
            "url": presentation.get("copy", {}).get("url") or "cocos://preview/" + material.get("slug", "asset"),
            "wordmark": str(override.get("wordmark") or "CreativeForge"),
            "wordmarkSub": "{} · AI Game Asset Factory".format(name),
        },
        "stac": [[w] for w in stac],  # 时间由 timeline_mapper 填充
    }


_NAME_PREFIXES = ("创建一个", "生成一个", "做一个", "创建", "生成", "制作")
_NAME_SUFFIXES = ("角色_带攻击动画", "_带攻击动画", "带攻击动画", "角色", "动画", "精灵")


def _display_name(raw: str) -> str:
    """资产名 → 合成 header 短名：剥生成指令前后缀、截断到 12 字。
    资产名常是整句 goal（"创建一个2d动漫风星辉剑士角色_带攻击动画"），
    直接上屏会挤爆 header——收敛为角色本名。"""

    text = raw.strip()
    for prefix in _NAME_PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix) + 2:
            text = text[len(prefix):]
            break
    for suffix in _NAME_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix) + 2:
            text = text[: -len(suffix)]
            break
    text = text.split("_")[0].strip()
    return text[:12] or raw[:12]


def _hook_from_prompt(prompt: str) -> list[str]:
    """从一句话目标派生三段 hook——只收 ≤8 字的实词短词；凑不满用通用
    默认（原始长句直接上屏是 PPT 观感的快车道）。"""

    words = [
        w.strip("，。,.！!？?、 ")
        for w in prompt.replace("，", " ").replace(",", " ").replace("_", " ").split()
    ]
    picked: list[str] = []
    for word in words:
        if 2 <= len(word) <= 8 and word not in picked:
            picked.append(word)
        if len(picked) == 3:
            break
    while len(picked) < 3:
        picked.append(DEFAULT_HOOK[len(picked)])
    return picked
