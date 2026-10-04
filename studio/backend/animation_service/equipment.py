"""角色装备/服装识别（V3.5）：看图认出武器/服装细节，反馈到两条生成链.

为什么需要：i2v 与骨骼动画都只吃「动作词」，不知道角色手里有剑、身上是
长裙还是重甲——attack 提示词不带武器约束时，i2v 常在快速挥击中把武器
挥丢/换手（帧粘连修复实测的伴生缺陷）；骨骼链的摆臂/步幅对持械、长裙、
重甲角色也应做贴合收缩。识别走视觉对话模型（settings ``vl_model``，
qwen-vl 系，OpenAI 兼容接口），按**源图哈希**持久缓存：同一张原画终身只
识别一次（~0.002 元/次），失败也缓存（TTL 1h，防网络抖动重试风暴）。

识别是增益项：模型不可用/响应异常/解析失败一律返回 None，绝不阻塞生成。
对外三个纯入口：
* ``recognize``        → 规范化装备 dict（含中文标签/中英摘要）或 None
* ``motion_clauses``   → i2v 动作提示词的追加子句（正向句，按动作注入）
* ``pose_overrides``   → 骨骼链 pose_config 的贴合覆盖（用户滑杆永远优先）
"""

import base64 as _b64
import hashlib
import io
import json
import os
import time

# 识别提示词：要求严格 JSON、字段封闭、描述「看到的」而非「猜的」。
# 小图预算：直接缩到 512px 送审（识别装备细节足够，token 减半）。
EQUIPMENT_PROMPT = (
    "你是游戏角色装备鉴定师。仔细观察这张角色立绘，只描述你确实看到的装备与"
    "服装，输出严格 JSON（不要 markdown 代码块、不要解释）：\n"
    '{"weapon": "武器名或空字符串（如 长剑/法杖/弓/斧/长枪/盾牌，没有武器'
    '必须为空字符串）", "armor": "none 或 light 或 heavy（heavy=金属铠甲/'
    "板甲/重甲，light=皮甲/布甲/轻甲）\", "
    '"skirt": true或false（裙/连衣裙/长袍下摆算 true）, '
    '"skirt_length": "none 或 short 或 long", '
    '"cape": true或false（披风/斗篷）, '
    '"hair": "short 或 long（及肩以下算 long）", '
    '"outfit": "服装的一句话中文描述（<=20字）", '
    '"accessories": ["可见的饰物名，最多5个，没有给空数组"]}\n'
    "注意：手持物品才算武器；背在背上的也算；画面里没有的绝对不要编。"
)

# 缓存：与 motion_prompt_cache.json 同目录（studio/backend/data/）。
_EQUIPMENT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "equipment_cache.json",
)
_EQUIPMENT_ERROR_TTL = 3600.0  # 失败条目 1 小时后过期（成功条目永久）
_EQUIPMENT_SEND_SIZE = 512  # 送审前缩边（识别装备细节足够，省 token）

_equipment_cache: dict = {}


def _load_equipment_cache() -> None:
    global _equipment_cache
    try:
        with open(_EQUIPMENT_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        _equipment_cache = data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        _equipment_cache = {}


def _save_equipment_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_EQUIPMENT_CACHE_PATH), exist_ok=True)
        with open(_EQUIPMENT_CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump(_equipment_cache, handle, ensure_ascii=False)
    except OSError:
        pass


_load_equipment_cache()


def _source_hash(source_bytes: bytes) -> str:
    return hashlib.sha1(source_bytes).hexdigest()[:12]


def _shrink(source_bytes: bytes) -> str:
    """源图 → 缩边后的 PNG data URL（识别不需要原分辨率）。"""

    from PIL import Image

    image = Image.open(io.BytesIO(source_bytes)).convert("RGB")
    image.thumbnail((_EQUIPMENT_SEND_SIZE, _EQUIPMENT_SEND_SIZE), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + _b64.b64encode(buffer.getvalue()).decode()


# ── 规范化词表 ─────────────────────────────────────────────────────────────
# 键=匹配词（小写），值=(规范类型, 中文标签)。武器名必须是「值出现在识别
# 文本中」的匹配词——首版把「剑」只写成 sword 的标签导致中文识别永远不
# 命中，词表必须中英文都覆盖。
_WEAPON_WORDS = {
    "sword": "sword",
    "长剑": "sword",
    "剑": "sword",
    "blade": "sword",
    "刀": "sword",
    "太刀": "sword",
    "katana": "sword",
    "匕首": "sword",
    "dagger": "sword",
    "axe": "axe",
    "斧": "axe",
    "hammer": "hammer",
    "锤": "hammer",
    "mace": "hammer",
    "spear": "spear",
    "长枪": "spear",
    "枪矛": "spear",
    "矛": "spear",
    "戟": "spear",
    "halberd": "spear",
    "lance": "spear",
    "枪": "spear",
    "bow": "bow",
    "弓": "bow",
    "箭": "bow",
    "staff": "staff",
    "法杖": "staff",
    "权杖": "staff",
    "杖": "staff",
    "wand": "staff",
    "scepter": "staff",
    "gun": "firearm",
    "火枪": "firearm",
    "枪械": "firearm",
    "rifle": "firearm",
    "pistol": "firearm",
    "shield": "shield",
    "盾": "shield",
}
_WEAPON_LABELS = {
    "sword": "武器·剑刃",
    "axe": "武器·斧",
    "hammer": "武器·锤",
    "spear": "武器·长柄",
    "bow": "武器·弓",
    "staff": "武器·法杖",
    "firearm": "武器·枪械",
    "shield": "盾牌",
    "other": "武器",
}
_WEAPON_EN = {
    "sword": "a bladed weapon",
    "axe": "an axe",
    "hammer": "a heavy hammer",
    "spear": "a long polearm",
    "bow": "a bow",
    "staff": "a staff",
    "firearm": "a firearm",
    "shield": "a shield",
    "other": "a held weapon",
}
_MELEE_WEAPONS = ("sword", "axe", "hammer", "spear")


def _match_weapon(text: str):
    """从识别文本里匹配武器类型。先长词后短词（「法杖」优先于「杖」）；
    裸「枪」有歧义（长枪/火枪），上下文无火器词时按长柄武器处理。"""

    text = text or ""
    lowered = text.lower()
    firearm_hints = ("火", "枪械", "射", "弹", "gun", "rifle", "pistol", "cannon")
    for word in sorted(_WEAPON_WORDS, key=len, reverse=True):
        if word in lowered or word in text:
            if word == "枪" and _match_any(text, firearm_hints):
                return "firearm"
            return _WEAPON_WORDS[word]
    return None


def _match_any(text, words):
    lowered = (text or "").lower()
    return any(word in lowered or word in (text or "") for word in words)


def _normalize(raw) -> dict | None:
    """模型原始 JSON → 规范化装备 dict。宽容解析：单字段非法只丢该字段。"""

    if not isinstance(raw, dict):
        return None

    def _text(key):
        value = raw.get(key)
        return str(value).strip() if value is not None else ""

    def _flag(key):
        return bool(raw.get(key))

    weapon = _match_weapon(_text("weapon"))
    armor = str(raw.get("armor") or "none").strip().lower()
    if armor not in ("none", "light", "heavy"):
        # 自由文本兜底：皮甲/轻甲/leather 归 light，其余带「甲/armor」归 heavy
        if _match_any(armor, ("皮甲", "轻甲", "布甲", "leather")):
            armor = "light"
        elif _match_any(armor, ("铠", "甲", "armor", "plate")):
            armor = "heavy"
        else:
            armor = "none"
    skirt = _flag("skirt") or _match_any(
        _text("skirt_length"), ("long", "short")
    )
    skirt_length = str(raw.get("skirt_length") or "").strip().lower()
    if skirt_length not in ("none", "short", "long"):
        skirt_length = "long" if skirt else "none"
    cape = _flag("cape") or _match_any(_text("outfit"), ("披风", "斗篷", "cape", "cloak"))
    hair = str(raw.get("hair") or "").strip().lower()
    if hair not in ("short", "long"):
        hair = "long" if _match_any(hair, ("long", "长")) else "short"
    accessories = [
        str(item).strip()[:12]
        for item in (raw.get("accessories") or [])[:5]
        if str(item or "").strip()
    ]

    labels = []
    if weapon:
        labels.append(_WEAPON_LABELS.get(weapon, "武器"))
    if armor == "heavy":
        labels.append("重甲")
    elif armor == "light":
        labels.append("轻甲")
    if skirt and skirt_length == "long":
        labels.append("长裙")
    elif skirt:
        labels.append("短裙")
    if cape:
        labels.append("披风")
    if hair == "long":
        labels.append("长发")
    for item in accessories[:3]:
        labels.append(item)

    summary_zh = "；".join(labels) if labels else ""
    en_parts = []
    if weapon:
        en_parts.append("wields {}".format(_WEAPON_EN.get(weapon, "a held weapon")))
    if armor == "heavy":
        en_parts.append("wears heavy armor")
    elif armor == "light":
        en_parts.append("wears light armor")
    if skirt and skirt_length == "long":
        en_parts.append("a long skirt or robe")
    elif skirt:
        en_parts.append("a short skirt")
    if cape:
        en_parts.append("a cape")
    if hair == "long":
        en_parts.append("long hair")
    if accessories:
        en_parts.append("accessories: " + ", ".join(accessories[:3]))
    summary_en = "; ".join(en_parts)

    return {
        "weapon": weapon,
        "weapon_label": _WEAPON_LABELS.get(weapon) if weapon else None,
        "armor": armor,
        "skirt": skirt,
        "skirt_length": skirt_length if skirt else "none",
        "cape": cape,
        "hair": hair,
        "outfit": _text("outfit")[:40],
        "accessories": accessories,
        "labels": labels,
        "summary_zh": summary_zh,
        "summary_en": summary_en,
    }


def cached_only(source_bytes: bytes) -> dict | None:
    """只读缓存查询（绝不触发模型调用）。NL 动作解读等零成本路径用。"""

    if not source_bytes:
        return None
    entry = _equipment_cache.get(_source_hash(source_bytes))
    if not isinstance(entry, dict) or "equipment" not in entry:
        return None
    return entry["equipment"] or None


def recognize(source_bytes: bytes, settings: dict | None) -> dict | None:
    """识别角色装备/服装（带持久缓存）。返回 None 表示不可用（未配置/
    失败/用户关闭），调用方按「无装备信息」继续。"""

    if not source_bytes:
        return None
    settings = settings or {}
    if not settings.get("equipment_aware", True):
        return None
    if not (settings.get("enabled") and settings.get("api_key")):
        return None

    key = _source_hash(source_bytes)
    entry = _equipment_cache.get(key)
    if isinstance(entry, dict):
        if "equipment" in entry:
            return entry["equipment"] or None
        # 失败条目：TTL 内直接复用失败结论，过期后允许重试
        if time.time() - float(entry.get("ts") or 0.0) < _EQUIPMENT_ERROR_TTL:
            return None

    try:
        from studio.backend.model_service.service import VisionChatProvider

        result = VisionChatProvider(settings).chat(
            EQUIPMENT_PROMPT,
            "识别这张角色立绘的装备与服装，输出严格 JSON。",
            _shrink(source_bytes),
        )
        raw_text = result.get("content") or ""
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON in vision output")
        equipment = _normalize(json.loads(raw_text[start : end + 1]))
        if equipment is None:
            raise ValueError("vision output not a JSON object")
    except Exception:  # noqa: BLE001 - 识别是增益项，失败不阻塞生成
        equipment = None

    # 失败也缓存（防重试风暴）；成功条目永久，失败条目带时间戳走 TTL
    _equipment_cache[key] = (
        {"equipment": equipment} if equipment else {"ts": time.time()}
    )
    _save_equipment_cache()
    return equipment


def context_line(equipment: dict | None) -> str | None:
    """i2v 动作润色的装备上下文行：中文标签 + **款式描述（outfit）**.

    outfit 是识别结果里唯一带「颜色/款式」细节的自由文本（如「白色金属
    质感紧身战甲」「灰色工装夹克与长裤」）——v3.5.1 前它被识别出来却从未
    进入润色上下文，润色模型只能靠泛型标签猜服装。润色模型是纯文本对话
    （看不到图），这里是它了解角色衣着的唯一通道。"""

    if not equipment:
        return None
    parts = []
    if equipment.get("summary_zh"):
        parts.append(equipment["summary_zh"])
    outfit = str(equipment.get("outfit") or "").strip()
    if outfit:
        parts.append(outfit)
    return "；".join(parts)[:200] or None


def motion_clauses(equipment: dict | None, action: str) -> list[str]:
    """i2v 动作提示词的装备子句（正向句，代码级追加——不交给润色模型发挥）。

    只在确凿的失败模式上花词预算：attack+持械（武器在快速挥击中最容易
    被挥丢/换手/融进手部）。walk/run 的服装跟随句 v2 词表已含（"Hair,
    cloth and loose accessories settle"），不重复注入以免稀释运动学目标。
    """

    if not equipment or not equipment.get("weapon"):
        return []
    if action != "attack":
        return []
    return [
        "The strike is delivered with the weapon the character already holds: "
        "the weapon stays firmly in the same hand and moves as one rigid piece "
        "with the arm through the entire swing."
    ]


def pose_overrides(equipment: dict | None, action: str) -> dict:
    """骨骼链 pose_config 贴合覆盖（保守幅度，用户显式参数永远优先）。

    * 持近战武器 + attack：摆臂加大（蓄力-发力对比更清晰，武器扫掠可见；
      v3.5 起 attack 消费 cfg arm——此前该覆盖是空操作）；
    * 重甲 + run：起伏收敛（甲重感；jump 弧线是动作身份、不受 cfg 缩放，
      故不覆盖 jump）;
    * 长裙 + walk/run：步幅微收（裙摆像素跟随大腿分区，大步幅易露接缝）。
    """

    if not equipment:
        return {}
    overrides: dict = {}
    weapon = equipment.get("weapon")
    if weapon in _MELEE_WEAPONS and action == "attack":
        overrides["arm"] = 1.25
    if equipment.get("armor") == "heavy" and action == "run":
        overrides["bob"] = 0.85
    if equipment.get("skirt") and equipment.get("skirt_length") == "long" and action in (
        "walk",
        "run",
    ):
        overrides["stride"] = 0.9
    return overrides
