"""Prompt -> structured character specification.

The generator is a deterministic *simulation* of an image model: the prompt is
parsed into an explicit CharacterSpec (gender / hair / expression / height /
body / outfit / weapon / element / action ...) plus a stable seed. Every later
stage (palette, sprite, animation, export) reads this spec, so different
prompts produce different assets while the same prompt always reproduces the
same asset.
"""

import hashlib
import json
import re

from precon._seed import clamp, rng

# --------------------------------------------------------------------------
# keyword tables (order matters: first match wins)
# --------------------------------------------------------------------------

GENDERS = [
    ("female", "女性", ("女性", "女生", "女孩", "女郎", "女神", "女巫", "女", "female", "woman", "girl", "she", "her")),
    ("male", "男性", ("男性", "男生", "男孩", "男爵", "国王", "男", "male", "man", "boy", "he", "his")),
    ("neutral", "无性别", ("无性别", "中性", "genderless", "neutral", "agender")),
]

CLASSES = [
    ("mage", "法师", ("法师", "术士", "巫师", "魔法师", "女巫", "巫妖", "witch", "wizard", "mage", "sorcerer", "warlock", "魔法")),
    ("warrior", "战士", ("战士", "骑士", "武士", "剑士", "重装", "warrior", "knight", "swordsman", "paladin")),
    ("archer", "弓箭手", ("弓箭手", "弓手", "游侠", "猎人", "神射", "archer", "ranger", "hunter")),
    ("rogue", "刺客", ("盗贼", "刺客", "忍者", "游荡", "rogue", "assassin", "thief", "ninja")),
    ("priest", "牧师", ("牧师", "祭司", "神官", "治愈", "僧侣", "priest", "cleric", "healer")),
    ("summoner", "召唤师", ("召唤师", "死灵", "亡灵", "necromancer", "summoner")),
    ("druid", "德鲁伊", ("德鲁伊", "druid")),
    ("monk", "武僧", ("武僧", "武师", "monk")),
    ("engineer", "机械师", ("机械师", "工程师", "枪手", "火枪", "engineer", "gunslinger")),
    ("bard", "吟游诗人", ("吟游", "bard")),
]

ELEMENTS = [
    ("fire", "火焰", ("火焰", "烈焰", "熔岩", "燃烧", "火球", "火系", "fire", "flame", "inferno", "ember")),
    ("ice", "冰霜", ("冰霜", "冰", "霜", "雪", "寒", "ice", "frost", "snow", "glacier")),
    ("lightning", "雷霆", ("闪电", "雷霆", "雷", "electric", "lightning", "thunder")),
    ("poison", "剧毒", ("剧毒", "毒", "poison", "venom")),
    ("nature", "自然", ("自然", "藤蔓", "森林", "德鲁伊", "nature", "forest", "druid")),
    ("water", "潮汐", ("潮汐", "海浪", "水元素", "water", "aqua")),
    ("wind", "疾风", ("疾风", "旋风", "龙卷", "wind", "gale")),
    ("holy", "神圣", ("神圣", "圣光", "holy", "divine", "radiant")),
    ("dark", "暗影", ("黑暗", "暗影", "虚空", "诅咒", "暗", "shadow", "void", "dark", "cursed")),
]

ELEMENT_COLORS = {
    "fire": {"base": "#e2562b", "accent": "#ff9d3d", "metal": "#a16207"},
    "ice": {"base": "#4cc2ff", "accent": "#bfeaff", "metal": "#7da7c9"},
    "lightning": {"base": "#8b7bff", "accent": "#ffe066", "metal": "#6b7280"},
    "poison": {"base": "#65a30d", "accent": "#bef264", "metal": "#4d7c0f"},
    "nature": {"base": "#34d399", "accent": "#a7f3d0", "metal": "#8a6f4d"},
    "water": {"base": "#0ea5e9", "accent": "#7dd3fc", "metal": "#64748b"},
    "wind": {"base": "#5eead4", "accent": "#e2fff8", "metal": "#94a3b8"},
    "holy": {"base": "#fbbf24", "accent": "#fff3c4", "metal": "#e5e7eb"},
    "dark": {"base": "#7c3aed", "accent": "#c4b5fd", "metal": "#4b5563"},
    "none": {"base": "#4cc2ff", "accent": "#ffd166", "metal": "#94a3b8"},
}

HAIR_COLORS = [
    ("silver", "银白", ("银白", "银色", "银发", "silver", "platinum", "银")),
    ("gold", "金色", ("金发", "金色", "blonde", "gold", "金")),
    ("black", "黑色", ("黑发", "黑色", "black", "黑")),
    ("red", "赤红", ("红发", "赤发", "绯红", "crimson", "ginger", "red", "红")),
    ("blue", "海蓝", ("蓝发", "青发", "azure", "blue", "蓝")),
    ("violet", "紫罗兰", ("紫发", "紫色", "purple", "violet", "紫")),
    ("green", "墨绿", ("绿发", "green", "绿")),
    ("brown", "栗棕", ("棕发", "褐色", "栗色", "brown", "chestnut", "棕", "褐")),
    ("pink", "樱粉", ("粉发", "粉色", "pink", "粉")),
    ("gray", "灰白", ("灰发", "灰色", "gray", "grey", "灰")),
    ("white", "白色", ("白发", "白色", "white", "白")),
]

HAIR_COLOR_HEX = {
    "silver": "#e9eef6", "white": "#f8fafc", "gold": "#f4d58d", "black": "#1b2230",
    "red": "#dc2626", "blue": "#4cc2ff", "violet": "#a78bfa", "green": "#34d399",
    "brown": "#a16207", "pink": "#fb7185", "gray": "#94a3b8",
}

HAIR_STYLES = [
    ("twin_tail", "双马尾", ("双马尾", "双辫", "twin", "twintail")),
    ("ponytail", "马尾", ("马尾", "ponytail")),
    ("braid", "编发", ("编发", "麻花辫", "辫子", "braid")),
    ("curly", "卷发", ("卷发", "波浪", "curly", "wavy")),
    ("straight", "直发", ("直发", "straight")),
    ("short", "短发", ("短发", "利落短发", "short")),
    ("long", "长发", ("长发", "披肩发", "long")),
    ("bald", "光头", ("光头", "秃", "bald")),
    ("bangs", "齐刘海", ("刘海", "bangs", "fringe")),
]

SKINS = [
    ("pale", "冷白", ("冷白", "白皙", "白皮", "苍白", "pale", "fair")),
    ("tan", "小麦", ("小麦", "古铜", "tan", "bronze")),
    ("dark", "深色", ("深色皮肤", "黑皮", "dark skin", "brown skin")),
    ("green", "兽人绿", ("绿皮", "兽人", "green skin", "orc")),
    ("blue", "幽蓝", ("蓝肤", "blue skin")),
]

SKIN_HEX = {
    "pale": "#f6e3d0", "tan": "#d8a26a", "dark": "#8a5a3b",
    "green": "#7fa650", "blue": "#8fc7e8", "default": "#eec6a2",
}

EYES = [
    ("slit", "竖瞳", ("竖瞳", "蛇瞳", "猎手瞳", "slit", "reptile")),
    ("heterochromia", "异色瞳", ("异色瞳", "双色瞳", "heterochromia")),
    ("amber", "琥珀", ("琥珀", "amber")),
    ("red", "猩红", ("红瞳", "血色瞳", "red eye", "crimson eye")),
    ("blue", "冰蓝", ("蓝瞳", "ice blue eye", "blue eye")),
    ("green", "翠绿", ("绿瞳", "green eye")),
    ("gold", "鎏金", ("金瞳", "gold eye")),
]

EYE_HEX = {
    "slit": "#ffb454", "heterochromia": "#a78bfa", "amber": "#ffb454",
    "red": "#fb7185", "blue": "#4cc2ff", "green": "#34d399", "gold": "#fbbf24",
}

EXPRESSIONS = [
    ("cold", "冷笑高傲", ("冷笑", "高冷", "冷酷", "冷漠", "高傲", "轻蔑", "冷峻", "cold", "arrogant")),
    ("angry", "愤怒狰狞", ("愤怒", "暴怒", "狰狞", "凶", "angry", "furious")),
    ("stern", "严肃沉稳", ("严肃", "认真", "沉稳", "威严", "stern", "serious")),
    ("mysterious", "神秘莫测", ("神秘", "诡秘", "阴郁", "mysterious", "enigmatic")),
    ("warm", "温和微笑", ("微笑", "温和", "温柔", "憨厚", "善良", "warm", "kind")),
    ("sad", "忧郁哀伤", ("悲伤", "忧郁", "哀伤", "sad", "melancholy")),
    ("cute", "天真可爱", ("可爱", "天真", "cute", "innocent")),
]

BUILDS = [
    ("slim", "修长偏瘦", ("修长", "纤细", "苗条", "偏瘦", "瘦", "slim", "slender")),
    ("muscular", "健壮魁梧", ("健壮", "魁梧", "肌肉", "强壮", "壮", "muscular", "burly")),
    ("petite", "娇小", ("娇小", "矮小", "矮", "petite", "tiny")),
    ("tall", "高大修长", ("高大", "高挑", "tall", "lanky")),
    ("plump", "圆润", ("圆润", "胖", "丰满", "plump", "chubby")),
]

ROLES = [
    ("boss", "首领", ("boss", "首领", "魔王", "头目", "老大", "领主")),
    ("npc", "NPC", ("npc", "村民", "商人", "铁匠", "守卫", "平民", "店员")),
    ("hero", "主角", ("hero", "主角", "英雄", "勇者")),
]

WEAPONS = [
    ("staff", "法杖", ("法杖", "魔杖", "权杖", "staff", "wand")),
    ("bow", "长弓", ("长弓", "弓箭", "弓", "bow")),
    ("dagger", "匕首", ("匕首", "短刀", "双刀", "dagger", "knife")),
    ("sword", "大剑", ("大剑", "长剑", "宝剑", "剑", "sword", "blade")),
    ("hammer", "战锤", ("战锤", "巨锤", "锤", "hammer", "mace")),
    ("axe", "战斧", ("战斧", "斧", "axe")),
    ("spear", "长枪", ("长枪", "长矛", "枪", "spear", "lance")),
    ("scythe", "镰刀", ("镰刀", "巨镰", "scythe")),
    ("shield", "盾", ("盾牌", "盾", "shield")),
    ("tome", "魔典", ("魔典", "法典", "魔法书", "tome", "grimoire")),
    ("orb", "法球", ("法球", "宝珠", "水晶球", "orb")),
]

CLASS_WEAPON = {
    "mage": "staff", "warrior": "sword", "archer": "bow", "rogue": "dagger",
    "priest": "tome", "summoner": "orb", "druid": "staff", "monk": "none",
    "engineer": "hammer", "bard": "none", "hero": "none",
}

ACCESSORIES = [
    ("wings", "羽翼", ("翅膀", "羽翼", "翼", "wings")),
    ("cape", "披风", ("披风", "斗篷", "cape", "cloak")),
    ("mask", "面罩", ("面罩", "面具", "mask")),
    ("crown", "王冠", ("王冠", "皇冠", "头冠", "crown", "tiara")),
    ("horns", "犄角", ("犄角", "恶魔角", "兽角", "龙角", "尖角", "horns")),
    ("halo", "光环", ("光环", "圣环", "halo")),
    ("necklace", "项链", ("项链", "吊坠", "necklace", "amulet")),
    ("goggles", "护目镜", ("护目镜", "goggles")),
    ("mech", "机械部件", ("机械臂", "义肢", "机械", "mech", "prosthetic")),
]

OUTFIT_COLORS = [
    ("#dc2626", ("红袍", "红衣", "红色", "赤", "绯", "red robe", "red")),
    ("#1b2230", ("黑袍", "黑衣", "黑色", "暗色", "black")),
    ("#4cc2ff", ("蓝袍", "蓝衣", "蓝色", "青色", "blue")),
    ("#e9eef6", ("白袍", "白衣", "白色", "white")),
    ("#34d399", ("绿袍", "绿衣", "绿色", "green")),
    ("#a78bfa", ("紫袍", "紫衣", "紫色", "purple")),
    ("#fbbf24", ("金袍", "金甲", "金色", "黄色", "gold")),
    ("#94a3b8", ("银甲", "灰色", "银色", "silver", "gray")),
    ("#a16207", ("棕袍", "褐色", "棕色", "brown")),
    ("#fb7185", ("粉袍", "粉色", "pink")),
]

ACTIONS = [
    ("attack", "attack", ("攻击", "施法", "挥砍", "射击", "attack", "cast", "strike")),
    ("walk", "walk", ("行走", "奔跑", "移动", "walk", "run")),
    ("idle", "idle", ("待机", "站立", "呼吸", "idle", "stand")),
]

STATIC_ITEMS = ("静态", "static", "单张", "still", "道具", "图标", "图块", "背景", "立绘", "头像", "icon", "tileset", "background", "item")

GARMENT_CONTEXT = ("袍", "衣", "甲", "服", "装", "裙", "铠", "披风", "斗篷", "外套", "战甲")

FRAME_COUNT = {"attack": 4, "walk": 6, "idle": 4}
FPS = {"attack": 12, "walk": 10, "idle": 8}


def _match(text, table, default=None):
    for value, *rest in table:
        keywords = rest[-1]
        if any(keyword in text for keyword in keywords):
            return value
    return default


def _match_outfit(text):
    """Matches an outfit colour only when the keyword sits next to a garment
    word — so hair/skin phrases like 银白色长发 never tint the clothes."""
    for hex_value, keywords in OUTFIT_COLORS:
        for keyword in keywords:
            start = 0
            while True:
                index = text.find(keyword, start)
                if index < 0:
                    break
                window = text[max(0, index - 3): index + len(keyword) + 5]
                if any(marker in window for marker in GARMENT_CONTEXT):
                    return hex_value
                start = index + 1
    return None


def _label(table, value, fallback=""):
    for entry in table:
        if entry[0] == value:
            return entry[1]
    return fallback


def _seed_from(goal):
    return int(hashlib.sha1(str(goal).encode("utf-8")).hexdigest()[:8], 16)


def _parse_height(text, build, gender, seed):
    match = re.search(r"(\d{3})\s*(?:cm|厘米|公分)?", text)
    if match:
        return int(clamp(int(match.group(1)), 120, 230))
    base = {"slim": 172, "muscular": 186, "petite": 155, "tall": 189, "plump": 167}.get(build, 172)
    if gender == "male":
        base += 5
    elif gender == "female":
        base -= 3
    return int(base + (seed % 9) - 4)


def compose_summary(spec):
    element = spec.get("element_label") if spec.get("element") not in (None, "none") else ""
    hair = "{} {}".format(
        spec.get("hair_color_label") or "", spec.get("hair_style_label") or ""
    ).strip()
    return "·".join(
        item for item in (
            spec.get("gender_label") or "未知",
            "{}{}".format(element, spec.get("class_label") or "冒险者"),
            hair,
            spec.get("expression_label") or "冷峻",
        ) if item
    )


HAIR_STYLE_LENGTH = {
    "long": "long", "curly": "long", "twin_tail": "long",
    "ponytail": "long", "braid": "long", "straight": "long",
    "short": "short", "bangs": "medium", "bald": "bald",
}

OVERRIDE_KEYS = (
    "gender", "class", "element", "hair_color", "hair_style",
    "expression", "build", "weapon", "action", "height_cm", "role", "static",
)


def apply_overrides(spec, overrides):
    """Applies user parameter overrides (Studio advanced controls).

    Empty/unknown values are ignored so the prompt-derived spec stays intact;
    a changed seed keeps the visual result distinct and reproducible.
    """
    if not overrides:
        return spec

    data = dict(spec)
    cleaned = {}
    for key in OVERRIDE_KEYS:
        value = overrides.get(key)
        if value in (None, "", "auto"):
            continue
        cleaned[key] = value

    if "gender" in cleaned and cleaned["gender"] in {entry[0] for entry in GENDERS}:
        data["gender"] = cleaned["gender"]
        data["gender_label"] = _label(GENDERS, data["gender"], "未知")
    if "class" in cleaned and cleaned["class"] in {entry[0] for entry in CLASSES}:
        data["class"] = cleaned["class"]
        data["class_label"] = _label(CLASSES, data["class"], "冒险者")
    if "element" in cleaned and cleaned["element"] in {entry[0] for entry in ELEMENTS}:
        data["element"] = cleaned["element"]
        data["element_label"] = _label(ELEMENTS, data["element"], "无")
    if "hair_color" in cleaned and cleaned["hair_color"] in HAIR_COLOR_HEX:
        data["hair_color"] = cleaned["hair_color"]
        data["hair_color_hex"] = HAIR_COLOR_HEX[data["hair_color"]]
        data["hair_color_label"] = _label(HAIR_COLORS, data["hair_color"], "黑色")
    if "hair_style" in cleaned and cleaned["hair_style"] in HAIR_STYLE_LENGTH:
        data["hair_style"] = cleaned["hair_style"]
        data["hair_style_label"] = _label(HAIR_STYLES, data["hair_style"], "长发")
        data["hair_length"] = HAIR_STYLE_LENGTH[data["hair_style"]]
    if "expression" in cleaned and cleaned["expression"] in {entry[0] for entry in EXPRESSIONS}:
        data["expression"] = cleaned["expression"]
        data["expression_label"] = _label(EXPRESSIONS, data["expression"], "冷峻")
    if "build" in cleaned and cleaned["build"] in {entry[0] for entry in BUILDS}:
        data["build"] = cleaned["build"]
        data["build_label"] = _label(BUILDS, data["build"], "标准")
    if "weapon" in cleaned and cleaned["weapon"] in {entry[0] for entry in WEAPONS} | {"none"}:
        data["weapon"] = cleaned["weapon"]
        data["weapon_label"] = _label(WEAPONS, data["weapon"], "无")
    if "action" in cleaned and cleaned["action"] in FRAME_COUNT:
        data["action"] = cleaned["action"]
        data["fps"] = FPS.get(data["action"], 12)
        data["frame_count"] = 1 if data.get("static") else FRAME_COUNT.get(data["action"], 4)
    if "role" in cleaned and cleaned["role"] in {entry[0] for entry in ROLES} | {"character"}:
        data["role"] = cleaned["role"]
        data["role_label"] = _label(ROLES, data["role"], "角色")
    if "height_cm" in cleaned:
        try:
            data["height_cm"] = int(clamp(int(cleaned["height_cm"]), 120, 230))
        except (TypeError, ValueError):
            pass
    if "static" in cleaned:
        data["static"] = bool(cleaned["static"])
        data["type"] = "prop" if data["static"] else "character"
        if data["static"]:
            data["frame_count"] = 1
            data["action"] = "idle"
            data["fps"] = 12

    seed_source = "{}|{}".format(
        data.get("goal", ""), json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    )
    data["seed"] = int(hashlib.sha1(seed_source.encode("utf-8")).hexdigest()[:8], 16)
    data["summary"] = compose_summary(data)
    return data


def parse_prompt(goal):
    """Parses a natural-language goal into a CharacterSpec dict."""
    text = str(goal or "").strip()
    lowered = text.lower()
    seed = _seed_from(text or "creativeforge")
    random = rng(seed, salt=7)

    gender = _match(lowered, GENDERS, "neutral")
    char_class = _match(lowered, CLASSES, "hero")
    element = _match(lowered, ELEMENTS, "none")
    role = _match(lowered, ROLES, "character")

    hair_color = _match(lowered, HAIR_COLORS)
    if hair_color is None:
        hair_color = ("black", "silver", "gold", "brown", "violet", "blue")[seed % 6]
    hair_style = _match(lowered, HAIR_STYLES)
    if hair_style is None:
        hair_style = ("long", "short", "ponytail", "braid")[seed % 4]
    hair_length = "long" if hair_style in ("long", "twin_tail", "ponytail", "braid", "curly") else (
        "bald" if hair_style == "bald" else "short"
    )

    skin = _match(lowered, SKINS, "default")
    eye_style = _match(lowered, EYES)
    if eye_style is None:
        eye_style = ("amber", "blue", "green", "red", "gold")[seed % 5]
    expression = _match(lowered, EXPRESSIONS, "cold")
    build = _match(lowered, BUILDS)
    if build is None:
        build = ("slim", "muscular", "tall", "petite")[seed % 4]

    accessory = [value for value, *rest in ACCESSORIES if any(k in lowered for k in rest[-1])]
    weapon = _match(lowered, WEAPONS)
    if weapon is None:
        weapon = CLASS_WEAPON.get(char_class, "none")
    outfit = _match_outfit(lowered)

    action = _match(lowered, ACTIONS, "idle")
    static = any(keyword in lowered for keyword in STATIC_ITEMS)

    height = _parse_height(text, build, gender, seed)

    element_label = _label(ELEMENTS, element, "无")

    data = {
        "goal": text,
        "seed": seed,
        "gender": gender,
        "gender_label": _label(GENDERS, gender, "未知"),
        "class": char_class,
        "class_label": _label(CLASSES, char_class, "冒险者"),
        "element": element,
        "element_label": element_label,
        "role": role,
        "role_label": _label(ROLES, role, "角色"),
        "height_cm": height,
        "build": build,
        "build_label": _label(BUILDS, build, "标准"),
        "hair_color": hair_color,
        "hair_color_hex": HAIR_COLOR_HEX.get(hair_color, "#1b2230"),
        "hair_color_label": _label(HAIR_COLORS, hair_color, "黑色"),
        "hair_style": hair_style,
        "hair_style_label": _label(HAIR_STYLES, hair_style, "长发"),
        "hair_length": hair_length,
        "skin": skin,
        "skin_hex": SKIN_HEX.get(skin, SKIN_HEX["default"]),
        "skin_label": _label(SKINS, skin, "标准"),
        "eyes": eye_style,
        "eyes_hex": EYE_HEX.get(eye_style, "#4cc2ff"),
        "eyes_label": _label(EYES, eye_style, "琥珀"),
        "expression": expression,
        "expression_label": _label(EXPRESSIONS, expression, "冷峻"),
        "outfit_hex": outfit,
        "outfit_label": "自定义配色" if outfit else element_label,
        "accessory": accessory,
        "weapon": weapon,
        "weapon_label": _label(WEAPONS, weapon, "无"),
        "action": action,
        "fps": FPS.get(action, 12),
        "frame_count": FRAME_COUNT.get(action, 4),
        "static": static,
        "style": "pixel",
        "type": "prop" if static else "character",
    }
    data["summary"] = compose_summary(data)
    return data
