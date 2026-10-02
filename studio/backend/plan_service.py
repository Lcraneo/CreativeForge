"""Dynamic Creative Planner (Phase 4).

Turns a natural-language goal into an **intent-driven** capability plan rather
than a fixed pipeline: only the capabilities the goal actually needs are
scheduled (e.g. a static 2D concept never schedules PReCon/FAlign/GImport; a
"walk animation" schedules FAlign; "import Unity" schedules GImport/unity;
editing an existing asset starts from the asset instead of regenerating one).

This is what ``POST /api/plan`` exposes to the Live Studio so the execution
plan appears *before* the task runs.
"""

ENGINE_KEYWORDS = {"unity": ("unity",), "cocos": ("cocos",), "godot": ("godot",)}

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
    "concept",
    "概念",
)
ANIMATION_KEYWORDS = (
    "动画",
    "animation",
    "待机",
    "idle",
    "攻击",
    "attack",
    "行走",
    "walk",
    "奔跑",
    "run",
    "跳跃",
    "jump",
    "动作",
)
PIXEL_KEYWORDS = ("像素", "pixel", "pixel art", "16x16", "32x32", "8-bit")
MODIFY_KEYWORDS = ("修改", "改成", "换成", "替换", "编辑", "调整为", "update", "edit", "modify")

AGENT_FOR_CAPABILITY = {
    "generation": "ArtAgent",
    "PReCon": "ArtAgent",
    "FAlign": "AnimationAgent",
    "GImport": "EngineAgent",
    "quality_check": "QAAgent",
    "motion_video_generation": "ShowcaseAgent",
}

CYCLE = ["generation", "PReCon", "FAlign", "GImport", "quality_check"]

SHOWCASE_KEYWORDS = ("发布视频", "宣传片", "showcase", "一镜到底", "demo 视频", "trailer", "发布片", "展示视频")

CAPABILITY_CATALOG = {
    "generation": {
        "agent": "ArtAgent",
        "action": "create_character",
        "label": "角色生成",
        "description": "自然语言 → 角色原画 + 资产结构（自定义模型或离线管线）",
    },
    "edit_asset": {
        "agent": "ArtAgent",
        "action": "edit_character",
        "label": "角色编辑",
        "description": "在现有资产基础上修改（换装/换色/风格迁移），不重掷身份",
    },
    "PReCon": {
        "agent": "ArtAgent",
        "action": "pixel_reconstruction",
        "label": "像素重建",
        "description": "网格推断 + 语义 16 色调色板 + 轮廓修复，产出像素游戏可用的精灵",
    },
    "FAlign": {
        "agent": "AnimationAgent",
        "action": "create_animation",
        "label": "动画对齐",
        "description": "锚点检测 / 运动相位对齐 / 根运动纠偏，动作帧时间轴一致",
    },
    "GImport": {
        "agent": "EngineAgent",
        "action": "export_engine",
        "label": "引擎导入",
        "description": "图集 / 动画剪辑 / Prefab / 运行时校验，一键导出引擎 zip",
    },
    "quality_check": {
        "agent": "QAAgent",
        "action": "quality_check",
        "label": "质量校验",
        "description": "像素 / 动画 / 引擎三路阈值门 + 修复轮",
    },
    "motion_video_generation": {
        "agent": "ShowcaseAgent",
        "action": "generate_showcase_video",
        "label": "发布视频生成",
        "description": "OneTake 外部能力：CreativeAsset → 一镜到底发布片（15s，onetake 渲染管线 + oracle 验收）",
    },
}


def capabilities() -> dict:
    """能力自省（P2 扩展性）：规划器当前可调度的能力清单及其语义，
    供前端/集成方发现能力，而无需读源码。"""

    return {
        "capabilities": [dict({"id": cap}, **meta) for cap, meta in CAPABILITY_CATALOG.items()],
        "engines": sorted(ENGINE_KEYWORDS.keys()),
        "cycle": CYCLE,
    }


def _has(text, keywords):
    return any(keyword in text for keyword in keywords)


def build_plan(goal: str, asset_id: str | None = None) -> dict:
    text = str(goal or "").lower()

    engine = "cocos"
    for name, keywords in ENGINE_KEYWORDS.items():
        if _has(text, keywords):
            engine = name
            break

    is_static = _has(text, STATIC_KEYWORDS)
    needs_animation = _has(text, ANIMATION_KEYWORDS) and not is_static
    is_pixel = _has(text, PIXEL_KEYWORDS)
    wants_engine = _has(text, tuple(k for kws in ENGINE_KEYWORDS.values() for k in kws))
    is_modify = bool(asset_id) or _has(text, MODIFY_KEYWORDS)

    # dynamic capability selection — only what the goal needs
    capabilities = []
    if is_modify and asset_id:
        capabilities.append("edit_asset")
    else:
        capabilities.append("generation")
    if is_pixel:
        capabilities.append("PReCon")
    if needs_animation:
        capabilities.append("FAlign")
    if wants_engine:
        capabilities.append("GImport")
    # quality gate only makes sense when there is a downstream processor
    if any(cap in capabilities for cap in ("PReCon", "FAlign", "GImport", "edit_asset")):
        capabilities.append("quality_check")
    # OneTake 发布片（External Creative Capability）：显式关键词触发，不进默认闭环
    if _has(text, SHOWCASE_KEYWORDS):
        capabilities.append("motion_video_generation")

    tasks = []
    for index, capability in enumerate(capabilities, start=1):
        task = {
            "id": "{:03d}".format(index),
            "capability": capability,
            "agent": AGENT_FOR_CAPABILITY.get(capability, "ArtAgent"),
            "action": _action_for(capability, engine),
        }
        if capability == "GImport":
            task["engine"] = engine
        tasks.append(task)

    return {
        "goal": goal,
        "asset_id": asset_id,
        "mode": "modify" if (is_modify and asset_id) else "create",
        "intent": {
            "engine": engine,
            "style": "pixel" if is_pixel else "2d",
            "animation": needs_animation,
            "static": is_static,
            "pixel": is_pixel,
            "modify": bool(is_modify),
            "engine_import": wants_engine,
        },
        "tasks": tasks,
    }


def _action_for(capability: str, engine: str) -> str:
    return {
        "generation": "create_character",
        "edit_asset": "edit_character",
        "PReCon": "pixel_reconstruction",
        "FAlign": "create_animation",
        "GImport": "export_{}".format(engine),
        "quality_check": "quality_check",
    }.get(capability, capability)
