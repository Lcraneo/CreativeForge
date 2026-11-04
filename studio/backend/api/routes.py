"""REST API for the Studio frontend."""

import base64
import json
import os
import re
import threading
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from studio.backend.idempotency import IdempotencyStore

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
_PREVIEW_FRAME_CACHE = {}  # (source_hash, action, config, size) -> [png bytes]
ANIMATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "animation"
)
# 生成类 POST 的幂等键（防双击/重发重复扣费）：键 TTL 与视频任务 TTL 同量级
_ANIM_TASK_IDEMPOTENCY = IdempotencyStore(ttl=3600.0)

# 三视图生成：按 asset_id 的互斥锁（防同一资产重复请求重复扣费），
# 以及整条链路的总 deadline（qwen 超时后不把 wanx 的 180s 再加一遍）。
_VIEW_GENERATION_TIMEOUT = 270.0
_VIEW_LOCKS: dict[str, threading.Lock] = {}
_VIEW_LOCKS_GUARD = threading.Lock()


def _view_lock(asset_id: str) -> threading.Lock:
    with _VIEW_LOCKS_GUARD:
        lock = _VIEW_LOCKS.get(asset_id)
        if lock is None:
            lock = threading.Lock()
            _VIEW_LOCKS[asset_id] = lock
        return lock


# 试玩舞台 rig/分割 mask 缓存（按 source_hash）：V2 渐进式加载会把条带请求
# 拆成多批（先 idle/walk，再 run/jump），没有这份内存缓存时第二批
# 请求会重复执行 AI 主体分割与骨架提取这两个昂贵步骤。rig 是轻量 dict、
# mask 是 256×256 单通道图，8 个角色约 0.5MB。
_PLAYTEST_RIG_CACHE: dict[str, tuple] = {}

# 试玩舞台动作视角策略：idle 用正面（呼吸待机），移动/跳跃用侧面。
# 试玩舞台默认不含 attack；PVE 敌人显式请求 attack 时仍按 PVE 自身视角
# 策略收集，避免删除试玩动作影响独立的战斗关卡。
# 只产出一套面向右侧的侧面素材，向左移动由 Canvas 水平镜像完成。
PLAYTEST_VIEW_BY_ACTION = {
    "idle": "front",
    "walk": "side",
    "run": "side",
    "jump": "side",
}


def _side_source_facing(asset: dict | None) -> str:
    """返回侧视源图朝向；新三视图显式写 right，旧记录按历史左向 prompt 推断。"""
    if not isinstance(asset, dict):
        return "left"
    views = asset.get("design_views")
    side = views.get("side") if isinstance(views, dict) else None
    if not isinstance(side, dict):
        return "left"
    facing = side.get("facing")
    if facing in ("left", "right"):
        return facing
    # 旧版 TURNAROUND_SHEET_PROMPT 明确要求“面朝画面左侧”；历史记录没有
    # facing 字段，按左向兼容，Canvas 会在向右移动时做一次水平镜像。
    return "left"

# ── 前端构建过期自检 ────────────────────────────────────────────────
# dist/index.html 落后于 src 最新 mtime → /health.frontend_stale=true →
# 前端页脚角标提示「请重新构建并强刷」。60s TTL 缓存避免每次健康检查全量
# 扫描；mtime 用文件级（Windows 上改文件内容不动目录 mtime）。
_FRONTEND_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
)
_FRONTEND_STALE_CACHE: tuple[float, bool] = (0.0, False)


def _frontend_build_stale() -> bool:
    global _FRONTEND_STALE_CACHE
    now = time.time()
    cached_at, stale = _FRONTEND_STALE_CACHE
    if now - cached_at < 60.0:
        return stale
    try:
        dist_mtime = os.path.getmtime(os.path.join(_FRONTEND_ROOT, "dist", "index.html"))
        newest_src = 0.0
        for folder in ("src", "public"):
            folder_path = os.path.join(_FRONTEND_ROOT, folder)
            if not os.path.isdir(folder_path):
                continue
            for root, _dirs, files in os.walk(folder_path):
                for name in files:
                    newest_src = max(newest_src, os.path.getmtime(os.path.join(root, name)))
        stale = newest_src > 0 and dist_mtime < newest_src
    except OSError:
        stale = False
    _FRONTEND_STALE_CACHE = (now, stale)
    return stale


# ── 试玩舞台 3D POC-0 ───────────────────────────────────────────────────
# 固定 GLB 夹具（离网验收）：皮肤/骨骼 + 5 个 animation clips，供前端 3D
# 舞台在没有真实 3D 资产时加载，验证「真实 GLB 加载 → 动画播放」链路。
_PLAYTEST3D_FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "playtest3d",
)
# 3D 舞台第一版只映射这 5 个标准动作；idle/walk/run 循环、jump/attack 一次性。
_PLAYTEST3D_ACTIONS = (
    {"name": "idle", "loop": True},
    {"name": "walk", "loop": True},
    {"name": "run", "loop": True},
    {"name": "jump", "loop": False},
    {"name": "attack", "loop": False},
)


def _playtest3d_error_manifest(asset_id: str, error: str, fallback_url: str) -> dict:
    """构造「不可用」的 3D 清单：错误状态 + 明确 2D 回退入口。"""

    return {
        "version": "1.0",
        "asset_id": asset_id,
        "available": False,
        "error": error,
        "mesh_url": None,
        "bytes": None,
        "sha256": None,
        "rig": None,
        "clips": [dict(action) for action in _PLAYTEST3D_ACTIONS],
        "fallback_url": fallback_url,
    }


def _playtest3d_fixture_manifest() -> dict:
    """返回离网验收用的固定夹具清单（manifest.json 即唯一事实源）。"""

    with open(os.path.join(_PLAYTEST3D_FIXTURE_DIR, "manifest.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _playtest3d_manifest_from_mesh(asset_id: str, mesh: dict | None) -> dict:
    """从资产 ``extensions.cloud_backends.mesh`` 槽位派生 3D 清单。"""

    import urllib.parse

    from adapters.cloud_backends.contracts import extension_v1 as contract

    fallback_url = "/playtest?asset=" + urllib.parse.quote(asset_id or "", safe="")
    if mesh is None:
        return _playtest3d_error_manifest(asset_id, "mesh_missing", fallback_url)
    if mesh.get("status") != "succeeded":
        return _playtest3d_error_manifest(asset_id, "mesh_failed", fallback_url)
    if mesh.get("format") not in ("glb",):
        return _playtest3d_error_manifest(asset_id, "unsupported_format", fallback_url)
    clean = contract.safe_rel_path(mesh.get("local_path"))
    if clean is None:
        return _playtest3d_error_manifest(asset_id, "path_invalid", fallback_url)
    try:
        if not os.path.isfile(contract.resolve_local_path(clean)):
            return _playtest3d_error_manifest(asset_id, "path_invalid", fallback_url)
    except contract.CloudExtensionError:
        return _playtest3d_error_manifest(asset_id, "path_invalid", fallback_url)
    return {
        "version": "1.0",
        "asset_id": asset_id,
        "available": True,
        "error": None,
        "mesh_url": "/api/cloud/artifacts/" + clean,
        "bytes": mesh.get("bytes"),
        "sha256": mesh.get("sha256"),
        "rig": {"provider": mesh.get("provider"), "rigged": bool(mesh.get("rigged", False))},
        "clips": [dict(action) for action in _PLAYTEST3D_ACTIONS],
        "fallback_url": fallback_url,
    }


def _resolve_asset(runtime, asset_id: str | None) -> dict | None:
    """Find an asset in the in-memory store, then in persistent history.

    The runtime asset store is empty after a restart, but the workbench can
    still be showing an image loaded from history — so the animation endpoint
    must resolve that asset too (otherwise it wrongly reports "no resource")."""
    if asset_id:
        asset = runtime.assets.get(asset_id)
        if asset is not None:
            return asset
        record = runtime.history.get(asset_id)
        if record and isinstance(record.get("asset"), dict):
            return record["asset"]
        for record in runtime.history.list(limit=200):
            candidate = record.get("asset")
            if isinstance(candidate, dict) and candidate.get("id") == asset_id:
                return candidate
        return None
    asset = runtime.assets.latest()
    if asset is not None:
        return asset
    records = runtime.history.list(limit=1)
    if records and isinstance(records[0].get("asset"), dict):
        return records[0]["asset"]
    return None


class CreateTaskRequest(BaseModel):
    goal: str
    overrides: dict | None = None
    turbo: bool = False  # 极速档：跳过三视图等增值步骤，最快出结果
    asset_id: str | None = None  # 有值 → 在该资产上继续（编辑/加动画）；空 → 创建全新资产


class AnimationRequest(BaseModel):
    asset_id: str | None = None
    image: str | None = None  # base64 PNG / JPEG source (optional)
    action: str = "walk"
    fps: int = 12
    duration: float = 1.0
    size: int = 512
    skeletal: bool = False  # 全身骨骼模式：关节动画而非源图变形
    view: str = "front"  # walk/run 的视角：front 正面 / side 侧视横版
    pose_config: dict | None = None  # 动作自定义参数（幅度/滞后/周期等）
    use_video: bool = False  # AI 视频驱动（Windup 式 i2v）：让 AI 原画本身动起来
    final_quality: bool = False  # 定稿档标记；视频模型固定 wan2.2-i2v-flash
    deform: str | None = None  # V3 网格变形开关："mesh"（默认）| "rigid"；None=跟随后端默认
    secondary_motion: bool = False  # V3 次级运动：发层摆动（首次生成发层约 0.3 元，之后缓存免费）
    equipment_aware: bool = True  # V3.5 装备/服装识别：看图认出武器/服装并贴合动作（首次 ~0.002 元，之后缓存免费）


class PreviewFrameRequest(BaseModel):
    asset_id: str | None = None
    action: str = "walk"
    view: str = "front"
    phase: float = 0.0  # 0..1 动作循环内相位
    size: int = 384
    pose_config: dict | None = None
    skeletal: bool = False  # 骨骼模式：预览当前角色绑定的骨架动画
    image: str | None = None  # 可选上传源图（base64），优先于 asset_id


class EnhanceRequest(BaseModel):
    goal: str
    overrides: dict | None = None


class SequenceRequest(BaseModel):
    frames: list[str]  # base64 PNG / JPEG frame images, in play order
    fps: int = 12
    size: int = 384


class AnalyzeRequest(BaseModel):
    image: str  # base64 source image


class ExportRequest(BaseModel):
    asset_id: str
    engine: str = "cocos"


class RollbackRequest(BaseModel):
    record_ids: list[str]


class ReviewRequest(BaseModel):
    asset_id: str
    approved: bool
    note: str | None = None


class VersionTagRequest(BaseModel):
    record_id: str
    tag: str  # approved / needs-work / none


class OpenFolderRequest(BaseModel):
    target: str  # generated / animation / exports


class ModelSettingsRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    chat_model: str | None = None
    edit_model: str | None = None
    video_model: str | None = None
    use_chat: bool | None = None
    use_image: bool | None = None
    use_video: bool | None = None
    size: str | None = None
    negative_prompt: str | None = None
    seed: str | None = None
    prompt_extend: bool | None = None
    watermark: bool | None = None
    video_size: str | None = None
    video_prompt_extend: bool | None = None
    video_ai_enhance: bool | None = None  # 动作描述 AI 增强（对话模型润色 i2v 提示词）
    image_fallback_policy: str | None = None  # 生图失败策略：strict（默认，报错终止）/ degrade（降级离线示意）
    timeout: int | None = None
    api_key_pool_add: list[str] | None = None  # 备用 Key 追加（每项一把）
    api_key_pool: list[str] | None = None  # 整池覆盖（清空传 []）
    api_key_pool_remove: list[int] | None = None  # 按池内序号移除（UI 拿到的是脱敏回显）


def _localize_asset(asset):
    """把资产里指向 DashScope OSS 的临时远程 URL 改写为本地代理
    ``/api/generated/<file>``。

    远程结果链接有三重裂图风险：浏览器网络环境可能无法直连 OSS、
    防盗链/Referer 策略、24 小时签名过期。生成时图片均已下载落盘
    （GENERATED_DIR，并由 artifact_store 同步到对象存储），本地代理同源且
    永久可达。

    注意：不能以「本地文件此刻是否存在」为改写条件——托管容器重新部署后
    磁盘是空的，若按存在性判断就会退回已过期的 OSS 链接；只要元数据里有
    file 名就改写，缺失的文件由 ``/api/generated`` 回源对象存储补齐。"""

    if not isinstance(asset, dict):
        return asset

    def localized(meta):
        if isinstance(meta, dict) and meta.get("file"):
            name = os.path.basename(str(meta["file"]))
            if name:
                return {**meta, "url": "/api/generated/" + name}
        return meta

    image = asset.get("image")
    if isinstance(image, dict):
        asset["image"] = localized(image)
    source = asset.get("source")
    if isinstance(source, dict) and isinstance(source.get("ai_image"), dict):
        source["ai_image"] = localized(source["ai_image"])

    views = asset.get("design_views")
    if isinstance(views, dict):
        image_file = (asset.get("image") or {}).get("file")
        for view in ("front", "side", "back"):
            meta = views.get(view)
            if not isinstance(meta, dict):
                continue
            if meta.get("file"):
                views[view] = localized(meta)
            elif view == "front" and image_file:
                # front 视图复用原画：用原画的本地文件回写
                local = localized({"file": image_file, "url": meta.get("url"), "model": meta.get("model")})
                if str(local.get("url", "")).startswith("/api/generated/"):
                    views[view] = {**meta, "url": local["url"]}

    return asset


def _localize_history_record(record):
    """历史记录的顶层 image 与内嵌 asset 都做 URL 本地化。"""

    asset = record.get("asset")
    if isinstance(asset, dict):
        record["asset"] = _localize_asset(asset)
    image = record.get("image")
    if isinstance(image, dict) and image.get("file"):
        name = os.path.basename(str(image["file"]))
        if name:
            record["image"] = {**image, "url": "/api/generated/" + name}
    return record


def _enhance_context_for(asset) -> str | None:
    """角色名 + 规格摘要，作为视频动作描述 AI 增强的上下文（无则 None）。"""

    if not isinstance(asset, dict):
        return None
    parts = []
    if asset.get("name"):
        parts.append(str(asset["name"]))
    summary = (asset.get("character") or {}).get("summary")
    if summary:
        parts.append(str(summary))
    return ("；".join(parts)[:200]) or None


def build_router(runtime):
    router = APIRouter(prefix="/api")

    @router.post("/tasks", status_code=202)
    def create_task(request: CreateTaskRequest):
        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="goal is required")
        # 仅当显式传了 asset_id 才继续现有资产；不带 asset_id 一律创建全新
        # 资产，避免"想新建角色却被历史资产劫持"的上下文污染（Phase 4 §6）。
        asset = _resolve_asset(runtime, request.asset_id) if request.asset_id else None
        task_id = runtime.start_task(
            goal,
            overrides=request.overrides,
            turbo=request.turbo,
            asset=asset,
        )
        return {
            "task_id": task_id,
            "status": "running",
            "stream_url": "/ws/tasks/{}/stream".format(task_id),
        }

    @router.get("/tasks")
    def list_tasks():
        return {"tasks": runtime.tasks.list()}

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        task = runtime.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="unknown task")
        result = task.get("result") or {}
        return {
            "task_id": task["task_id"],
            "goal": task["goal"],
            "status": task["status"],
            "plan": task["plan"],
            "asset_id": task["asset_id"],
            "error": task["error"],
            "events": task["events"],
            "supervisor": result.get("supervisor"),
            "messages": result.get("messages"),
        }

    @router.get("/assets")
    def list_assets():
        return {"assets": runtime.assets.list()}

    @router.get("/assets/latest")
    def latest_asset():
        # 内存为空（后端重启后）时回退到落盘历史——否则打开动画工作台
        # 必弹 "no asset yet" 请求失败，而资产明明都在历史里
        asset = _resolve_asset(runtime, None)
        if asset is None:
            raise HTTPException(status_code=404, detail="no asset yet")
        return _localize_asset(asset)

    @router.get("/assets/{asset_id}")
    def get_asset(asset_id: str):
        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        return _localize_asset(asset)

    @router.get("/assets/{asset_id}/image.png")
    def asset_image(asset_id: str, view: str = "front", size: int = 512):
        """资产头像图：优先返回资产的真实原画（AI 生成图/上传源图），资产
        确实没有真实图时才回落程序化矢量角色。

        回落小熊修复：旧版无条件 render_asset_view，有 AI 原画的资产也会被
        程序化橙熊冒名顶替（动画链路实际绑定的是真实原画，头像与rig 不一致
        会误导排查）。view 参数只对程序化路径有意义——真实原画只有一张。"""
        from artgen import render_asset_view
        from studio.backend.animation_service.service import AnimationService

        # 也从历史解析：重启后工作台仍会展示历史资产图，动画/预览共用此图
        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        bounded = max(64, min(1024, int(size)))
        real_art = None
        try:
            real_art = AnimationService(ANIMATION_DIR)._asset_render(asset)
        except Exception:  # noqa: BLE001 - 原画解析失败回落程序化渲染
            real_art = None
        if real_art is not None:
            import io as _io

            from PIL import Image as PILImage

            image = PILImage.open(_io.BytesIO(real_art)).convert("RGBA")
            image.thumbnail((bounded, bounded), PILImage.LANCZOS)
            buffer = _io.BytesIO()
            image.save(buffer, "PNG")
            content = buffer.getvalue()
        else:
            content = render_asset_view(asset, view=view, size=bounded)
        return Response(
            content=content,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Image-Style": "2d",
                "X-Image-View": view,
                "X-Image-Source": "real-art" if real_art is not None else "procedural",
            },
        )

    @router.get("/assets/{asset_id}/views.png")
    def asset_views(asset_id: str, size: int = 512, gap: int = 24):
        """Three-view character sheet (front | side | top)."""
        from artgen import render_asset_sheet

        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        bounded = max(64, min(768, int(size)))
        return Response(
            content=render_asset_sheet(asset, size=bounded, gap=max(0, int(gap))),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Image-Style": "2d",
                "X-Image-View": "front,side,top",
            },
        )

    @router.post("/export")
    def export_asset(request: ExportRequest):
        from studio.backend.export_service.service import ExportService

        # 历史兜底（_resolve_asset）：内存 store 重启即空，工作台可能正
        # 展示着历史资产——单资产导出曾因此对一切历史资产 404（同类坑
        # 已在 latest/animation 修过，此处补齐）
        asset = _resolve_asset(runtime, request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        if request.engine not in ("unity", "cocos", "godot"):
            raise HTTPException(status_code=422, detail="unknown engine")
        service = ExportService(EXPORTS_DIR)
        return service.export(asset, request.engine)

    @router.post("/export/character-package")
    def export_character_package_route(request: dict):
        """角色资产包一键导出：一个角色 = 原画 + 三视图 + 全动作 GIF +
        引擎工程包（GImport），单个 zip 交付。"""

        from studio.backend.animation_service.service import AnimationService
        from studio.backend.export_service.character_package import (
            export_character_package,
        )

        asset = _resolve_asset(runtime, (request or {}).get("asset_id") or "")
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        engine = request.get("engine") or "cocos"
        if engine not in ("unity", "cocos", "godot"):
            raise HTTPException(status_code=422, detail="unknown engine")
        animations = AnimationService(ANIMATION_DIR).animations_for_asset(asset.get("id"))
        try:
            result = export_character_package(
                dict(asset), animations, EXPORTS_DIR, engine=engine
            )
        except Exception as error:  # noqa: BLE001 - 组装失败要给出可读原因
            raise HTTPException(status_code=502, detail=str(error)[:200])
        result.pop("path", None)
        return result

    @router.get("/exports/{package_name}")
    def download_package(package_name: str):
        path = os.path.join(EXPORTS_DIR, package_name)
        if not os.path.isfile(path) or not package_name.endswith(".zip"):
            raise HTTPException(status_code=404, detail="unknown package")
        return FileResponse(path, media_type="application/zip", filename=package_name)

    @router.get("/history")
    def list_history(
        engine: str = None,
        q: str = None,
        limit: int = 100,
        kind: str = None,
    ):
        if kind not in (None, "", "all", "character", "pve_enemy"):
            raise HTTPException(status_code=422, detail="kind must be character or pve_enemy")
        kind = kind or None
        records = [
            _localize_history_record(record)
            for record in runtime.history.list(limit=limit, engine=engine, keyword=q, kind=kind)
        ]
        return {"records": records, "total": runtime.history.count(kind=kind)}

    @router.get("/history/{record_id}")
    def get_history(record_id: str):
        record = runtime.history.get(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown history record")
        return _localize_history_record(record)

    @router.delete("/history/{record_id}")
    def delete_history(record_id: str):
        removed = runtime.history.delete(record_id)
        if not removed:
            raise HTTPException(status_code=404, detail="unknown history record")
        return {"status": "deleted", "removed": removed}

    @router.delete("/history")
    def clear_history():
        runtime.history.clear()
        return {"status": "cleared"}

    # ------------------------------------------------------------------
    # third-party image model settings
    # ------------------------------------------------------------------

    @router.get("/settings/model")
    def get_model_settings():
        return runtime.model_settings.public()

    @router.get("/settings/model/presets")
    def get_model_presets():
        from studio.backend.model_service.service import PROVIDER_PRESETS

        return {"presets": PROVIDER_PRESETS}

    _SIZE_PATTERN = re.compile(r"^\d{2,4}[x*]\d{2,4}$")

    def _validate_settings_payload(payload: dict) -> None:
        """API 配置参数校验（P1）：字段格式 + 启用态跨字段完整性，非法 422。"""

        errors = []
        base_url = payload.get("base_url")
        if base_url is not None and base_url and not str(base_url).startswith(("http://", "https://")):
            errors.append("Base URL 必须以 http:// 或 https:// 开头")
        api_key = payload.get("api_key")
        if api_key is not None and api_key and (" " in api_key or api_key != api_key.strip()):
            errors.append("API Key 不能包含空格")
        for field, label in (("size", "生图尺寸"), ("video_size", "视频尺寸")):
            value = payload.get(field)
            if value is not None and value and not _SIZE_PATTERN.match(str(value)):
                errors.append("{}格式应为 宽x高（如 1024x1024 或 1280*720）".format(label))
        timeout = payload.get("timeout")
        if timeout is not None:
            try:
                if not 10 <= int(timeout) <= 600:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("超时需在 10~600 秒之间")

        # 启用态跨字段完整性：合并现有配置后再检查
        merged = dict(runtime.model_settings.effective())
        merged.update({k: v for k, v in payload.items() if v is not None})
        if merged.get("enabled"):
            if not merged.get("base_url"):
                errors.append("启用自定义模型时 Base URL 不能为空")
            if not merged.get("api_key"):
                errors.append("启用自定义模型时 API Key 不能为空（留空请关闭开关走离线管线）")
            if merged.get("use_image") and not merged.get("model"):
                errors.append("启用图像生成时必须填写图像模型 model（视频模型可留空走服务商默认）")
        if errors:
            raise HTTPException(status_code=422, detail="；".join(errors))

    @router.put("/settings/model")
    def update_model_settings(request: ModelSettingsRequest):
        payload = request.model_dump(exclude_unset=True)
        _validate_settings_payload(payload)
        return runtime.model_settings.update(payload)

    @router.post("/settings/model/test")
    def test_model_settings():
        from studio.backend.model_service.service import ImageProvider

        return ImageProvider(runtime.model_settings.effective()).test()

    @router.delete("/settings/model/key")
    def clear_model_key():
        return runtime.model_settings.clear_key()

    @router.get("/settings/model/usage")
    def model_usage():
        """额度仪表：本地估算的用量台账（非账单）。"""

        from studio.backend.model_service import usage as usage_store

        return usage_store.usage_summary()

    @router.delete("/settings/model/usage")
    def model_usage_clear():
        from studio.backend.model_service import usage as usage_store

        usage_store.clear_usage()
        return {"status": "cleared"}

    @router.post("/prompt/enhance")
    def enhance_prompt(request: EnhanceRequest):
        """手动提示词增强（对话框按钮触发，替代原先的自动增强）。"""
        from agent.generation.spec import apply_overrides, parse_prompt
        from studio.backend.model_service.service import ChatProvider

        settings = runtime.model_settings.effective()
        if not (
            settings.get("enabled")
            and settings.get("api_key")
            and settings.get("chat_model")
            and settings.get("use_chat", True)
        ):
            raise HTTPException(
                status_code=409,
                detail="提示词增强需要先在「模型设置」启用并配置对话模型（chat_model）",
            )
        goal = (request.goal or "").strip()
        if not goal:
            raise HTTPException(status_code=422, detail="goal is required")
        spec = apply_overrides(parse_prompt(goal), request.overrides)
        try:
            return ChatProvider(settings).enhance(goal, spec, request.overrides)
        except Exception as error:  # noqa: BLE001 - surface provider error
            raise HTTPException(status_code=502, detail=str(error))

    @router.get("/generated/{name}")
    def generated_image(name: str):
        from studio.backend import artifact_store
        from studio.backend.model_service.service import safe_generated_path

        path = safe_generated_path(name)
        if path is None:
            # 托管容器无持久盘：本地缺失时回源对象存储再落盘
            path = artifact_store.ensure_local("generated/" + os.path.basename(name))
        if path is None:
            raise HTTPException(status_code=404, detail="unknown image")
        return FileResponse(path)

    # ── 三视图生成 ────────────────────────────────────────────────────

    @router.post("/design/views")
    def generate_design_views(request: dict):
        """手动触发的三视图生成：front 直接取资产原画，仅派生 side / back。

        角色生成阶段不再自动调用此接口；只有设计中心的按钮会发请求。"""
        from studio.backend.model_service.service import (
            _keys_for,
            generate_turnaround,
            safe_generated_path,
        )

        asset_id = str(request.get("asset_id") or "")
        asset = _resolve_asset(runtime, asset_id) if asset_id else None
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        source_image = asset.get("image")
        if not isinstance(source_image, dict) or not source_image.get("file") or not source_image.get(
            "url"
        ):
            raise HTTPException(status_code=409, detail="该资产没有可用的 AI 原画")

        local_path = safe_generated_path(source_image.get("file"))
        readable = False
        if local_path:
            try:
                with open(local_path, "rb") as handle:
                    handle.read(1)
                readable = True
            except OSError:
                readable = False
        if not readable:
            raise HTTPException(status_code=409, detail="该资产没有可用的 AI 原画")

        settings = runtime.model_settings.effective()
        if not settings.get("enabled") or not _keys_for(settings):
            raise HTTPException(status_code=409, detail="自定义模型未启用或缺少 API Key")

        # 同一资产并发请求会重复扣费：拿不到锁直接返回可理解的状态
        lock = _view_lock(asset_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="该资产的三视图正在生成中，请稍候再试")

        deadline = time.time() + _VIEW_GENERATION_TIMEOUT
        try:
            try:
                views, failures = generate_turnaround(
                    settings,
                    source_image.get("url"),
                    front_image=source_image,
                    deadline=deadline,
                )
            except Exception as error:  # noqa: BLE001 - surface real provider / validation error
                raise HTTPException(status_code=502, detail=str(error))

            if not (views.get("side") and views.get("back")):
                # 三视图必须三栏齐全；缺任何一侧都不写入 design_views
                raise HTTPException(
                    status_code=502, detail="；".join(failures) or "side / back 未完整生成"
                )

            # 成功后整体更新三视图；旧版本仅在失败时保留
            existing = asset.get("design_views")
            merged = {**(existing if isinstance(existing, dict) else {}), **views}
            asset["design_views"] = merged
            runtime.assets.save(asset)
            runtime.history.patch_asset(asset_id, {"design_views": merged})
            return {
                "design_views": merged,
                "failures": failures,
                "model": views["side"].get("model"),
                "status": "success",
            }
        finally:
            lock.release()

    # ------------------------------------------------------------------
    # animation (style-consistent generation from an image)
    # ------------------------------------------------------------------

    @router.post("/animation")
    def create_animation(request: AnimationRequest):
        from studio.backend.animation_service.service import AnimationService

        service = AnimationService(ANIMATION_DIR)
        image_bytes = None
        if request.image:
            try:
                image_bytes = base64.b64decode(request.image.split(",")[-1])
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="image 不是合法的 base64")

        asset = _resolve_asset(runtime, request.asset_id)
        if asset is None and image_bytes is None:
            raise HTTPException(
                status_code=404,
                detail="没有可用资源：请先在工作台生成资产，或上传一张源图",
            )
        if request.use_video:
            # Windup 式 i2v：源图 + 动作提示词 → 图生视频 → 抽帧合成
            source = image_bytes or service._asset_render(asset, view=request.view)
            if not source:
                raise HTTPException(status_code=409, detail="该资产没有可用的 AI 原画")
            settings = runtime.model_settings.effective()
            if not (settings.get("enabled") and settings.get("api_key")):
                raise HTTPException(
                    status_code=409, detail="AI 视频驱动需要先在模型设置中启用自定义模型"
                )
            if not settings.get("use_video", True):
                raise HTTPException(
                    status_code=409, detail="视频生成已在「模型设置」中关闭（视频能力开关）"
                )
            try:
                return service.create_video(
                    source_bytes=source,
                    settings=settings,
                    action=request.action,
                    fps=request.fps,
                    duration=request.duration,
                    size=request.size,
                    asset_id=request.asset_id or (asset.get("id") if asset else None),
                    enhance_context=_enhance_context_for(asset),
                    final_quality=request.final_quality,
                    equipment_aware=request.equipment_aware,
                    view=request.view,
                    source_facing=(
                        _side_source_facing(asset) if request.view == "side" else None
                    ),
                )
            except RuntimeError as error:
                raise HTTPException(status_code=502, detail=str(error))
            except OSError as error:
                # 源图无法解码（PIL UnidentifiedImageError 是 OSError 子类）
                raise HTTPException(status_code=400, detail="源图无法解码：{}".format(str(error)[:140]))
        # V3 网格变形：deform 注入 pose_config 的保留键 skin（riganim 读取），
        # 不污染用户滑杆参数
        pose_config = dict(request.pose_config or {})
        if request.deform in ("mesh", "rigid"):
            pose_config["skin"] = request.deform
        try:
            return service.create(
                asset=asset,
                image_bytes=image_bytes,
                action=request.action,
                fps=request.fps,
                duration=request.duration,
                size=request.size,
                skeletal=request.skeletal,
                view=request.view,
                pose_config=pose_config or None,
                model_settings=runtime.model_settings.effective(),
                secondary_motion=request.secondary_motion,
                equipment_aware=request.equipment_aware,
            )
        except (ValueError, OSError) as error:
            # OSError：PIL UnidentifiedImageError 继承链是 OSError——垃圾图
            # (2MB 非法字节)曾以 500 裸奔，错误处理需显式归一为 400
            raise HTTPException(status_code=400, detail=str(error)[:200])

    @router.post("/animation/tasks", status_code=202)
    def start_animation_task(request: AnimationRequest, http_request: Request):
        """生成任务化（体验优化）：与 POST /api/animation 同请求体，但立即
        返回 task_id 供前端轮询（阶段进度 + 刷新后凭 localStorage 续接）。
        仅 AI 视频链（60~90s 大头）有必要任务化；同步端点原样保留，骨骼/
        序列帧路径不受影响。前置校验与同步分支同语义（404/409 即刻返回）。

        幂等：客户端每次用户提交生成 ``Idempotency-Key`` 请求头——同键且
        已存任务仍在运行时直接返回已存快照，不重复入队、不重复扣费。"""

        from studio.backend.animation_service.service import AnimationService

        idem_key = (http_request.headers.get("idempotency-key") or "").strip()[:80]
        stored = _ANIM_TASK_IDEMPOTENCY.get(idem_key) if idem_key else None
        if isinstance(stored, dict) and (stored.get("snapshot") or {}).get("status") == "running":
            return stored

        service = AnimationService(ANIMATION_DIR)
        image_bytes = None
        if request.image:
            try:
                image_bytes = base64.b64decode(request.image.split(",")[-1])
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="image 不是合法的 base64")

        asset = _resolve_asset(runtime, request.asset_id)
        if asset is None and image_bytes is None:
            raise HTTPException(
                status_code=404,
                detail="没有可用资源：请先在工作台生成资产，或上传一张源图",
            )
        source = image_bytes or service._asset_render(asset, view=request.view)
        if not source:
            raise HTTPException(status_code=409, detail="该资产没有可用的 AI 原画")
        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(
                status_code=409, detail="AI 视频驱动需要先在模型设置中启用自定义模型"
            )
        if not settings.get("use_video", True):
            raise HTTPException(
                status_code=409, detail="视频生成已在「模型设置」中关闭（视频能力开关）"
            )
        snapshot = service.start_video_task(
            source_bytes=source,
            settings=settings,
            action=request.action,
            fps=request.fps,
            duration=request.duration,
            size=request.size,
            asset_id=request.asset_id or (asset.get("id") if asset else None),
            enhance_context=_enhance_context_for(asset),
            final_quality=request.final_quality,
            equipment_aware=request.equipment_aware,
            view=request.view,
            source_facing=(_side_source_facing(asset) if request.view == "side" else None),
        )
        payload = {"task_id": snapshot["id"], "snapshot": snapshot}
        if idem_key:
            _ANIM_TASK_IDEMPOTENCY.put(idem_key, payload)
        return payload

    @router.get("/animation/tasks/{task_id}")
    def animation_task_status(task_id: str):
        """视频生成任务状态轮询：running 带 stage/progress；终态带 result
        （成功）或 error/error_kind（失败，与批次同款分类）。"""

        from studio.backend.animation_service.service import AnimationService

        snapshot = AnimationService(ANIMATION_DIR).video_task_snapshot(task_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return snapshot

    @router.post("/animation/preview-frame")
    def preview_animation_frame(request: PreviewFrameRequest):
        """渲染动作循环内的单帧 PNG（动作编辑器的时间轴/滑杆实时预览）。"""
        from artgen import asset_params
        from artgen.anim import render_frame_rgba
        from artgen.png import encode_rgba
        from artgen.sidewalk import render_side_frame_rgba

        params = {"palette": None, "seed": "preview"}
        if request.asset_id:
            asset = _resolve_asset(runtime, request.asset_id)
            if asset is not None:
                params = asset_params(asset)
        view = request.view if request.view in ("front", "side") else "front"
        phase = max(0.0, min(1.0, float(request.phase)))
        action = (
            request.action
            if request.action in ("idle", "walk", "run", "attack", "jump")
            else "walk"
        )

        if request.skeletal:
            # 骨骼预览：使用当前角色绑定的骨架（与工作台生成同一条链路）。
            # 帧缓存：同一（源图/动作/参数）只渲染一次 24 帧，时间轴拖动与
            # 播放循环直接取帧——否则每次请求重渲染 24 帧会明显卡顿。
            source = None
            if request.image:
                try:
                    source = base64.b64decode(request.image.split(",")[-1])
                except (ValueError, TypeError):
                    raise HTTPException(status_code=422, detail="image 不是合法的 base64")
            elif request.asset_id:
                asset = _resolve_asset(runtime, request.asset_id)
                if asset is not None:
                    from studio.backend.animation_service.service import AnimationService

                    source = AnimationService(ANIMATION_DIR)._asset_render(asset)
                    if source is None:
                        # 有原画记录但拉不到（本机缺失 + 远端签名失效）时，
                        # 程序化兜底会用另一个形象冒充该角色——预览"不是
                        # 原画"就是这么来的。明确报错让前端提示，只对本来
                        # 就没有原画记录的资产才回落程序化渲染。
                        art_meta = [
                            asset.get("image"),
                            (asset.get("source") or {}).get("ai_image"),
                        ]
                        if any(
                            isinstance(m, dict) and (m.get("file") or m.get("url") or m.get("path"))
                            for m in art_meta
                        ):
                            raise HTTPException(
                                status_code=409,
                                detail="该资产的 AI 原画在本机缺失且远端链接已失效，无法按原画预览（原画由其他设备生成时需重新生成）",
                            )
                        from artgen import render_asset_view

                        source = render_asset_view(
                            asset, "front", max(384, min(1024, request.size))
                        )
            if source is None:
                raise HTTPException(
                    status_code=400, detail="骨骼预览需要真实角色源图（资产原画或上传图片）"
                )

            import hashlib as _hashlib

            source_hash = _hashlib.sha1(source).hexdigest()[:12]
            config_key = json.dumps(request.pose_config or {}, sort_keys=True, ensure_ascii=False)
            cache_key = (source_hash, action, config_key, request.size)
            frames = _PREVIEW_FRAME_CACHE.get(cache_key)
            if frames is None:
                from artgen.rig import build_rig
                from artgen.riganim import animate_rigged
                from studio.backend.animation_service.service import (
                    AnimationService as _AnimService,
                    ai_segment_subject as _segment,
                )

                settings = runtime.model_settings.effective()
                mask = None
                if settings.get("enabled") and settings.get("api_key"):
                    try:
                        mask = _segment(source, 384, settings, deadline=time.time() + 90.0)
                    except Exception:  # noqa: BLE001
                        mask = None
                rig = build_rig(source, request.size, segment_mask=mask)
                frames_rgba, _ref, _rig, _falign = animate_rigged(
                    source, action, 24, request.size, rig=rig, config=request.pose_config, segment_mask=mask
                )
                frames = [encode_rgba(w, h, rgba) for w, h, rgba in frames_rgba]
                if len(_PREVIEW_FRAME_CACHE) >= 12:
                    _PREVIEW_FRAME_CACHE.pop(next(iter(_PREVIEW_FRAME_CACHE)))
                _PREVIEW_FRAME_CACHE[cache_key] = frames
            index = max(0, min(len(frames) - 1, int(round(phase * (len(frames) - 1)))))
            return Response(content=frames[index], media_type="image/png")

        if view == "side" and action in ("walk", "run"):
            w, h, rgba = render_side_frame_rgba(
                params, action, phase, request.size, request.pose_config
            )
        else:
            w, h, rgba = render_frame_rgba(params, action, phase, request.size, request.pose_config)
        return Response(content=encode_rgba(w, h, rgba), media_type="image/png")

    @router.post("/animation/batch-actions")
    def start_action_batch(request: dict):
        """一键补齐全套动作：为资产串行生成缺失动作的 AI 动画（视频驱动），
        已生成的自动跳过；``force_actions``（质检异常重试）强制重新生成。
        ``views_by_action`` 可让同一批同时使用正面与侧面源图；旧请求的
        ``view`` 仍作为整批默认视角。返回 batch_id 供轮询。"""

        from studio.backend.animation_service.service import (
            ACTIONS as ANIMATION_ACTIONS,
            DEFAULT_BATCH_VIEW_BY_ACTION,
            AnimationService,
        )

        asset = _resolve_asset(runtime, request.get("asset_id") or "")
        if asset is None:
            raise HTTPException(
                status_code=404,
                detail="unknown asset: 角色资产已不存在（可能因服务重启丢失），请重新生成角色后再补动作",
            )
        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="AI 动画生成需要先启用自定义模型")

        service = AnimationService(ANIMATION_DIR)
        requested_actions = request.get("actions")
        actions = [
            action
            for action in (
                requested_actions if requested_actions is not None else ANIMATION_ACTIONS
            )
            if action in ANIMATION_ACTIONS
        ]
        requested_views = request.get("views_by_action")
        requested_views = requested_views if isinstance(requested_views, dict) else {}
        fallback_view = request.get("view")
        views_by_action = {}
        for action in actions:
            candidate = requested_views.get(action)
            if candidate not in ("front", "side"):
                candidate = (
                    fallback_view
                    if fallback_view in ("front", "side")
                    else DEFAULT_BATCH_VIEW_BY_ACTION[action]
                )
            views_by_action[action] = candidate

        force_actions = request.get("force_actions")
        force_actions = force_actions if isinstance(force_actions, list) else []
        forced = {action for action in force_actions if action in ANIMATION_ACTIONS}
        done = service.existing_ai_actions(asset.get("id"), expected_views=views_by_action)
        needed_actions = [action for action in actions if action not in done or action in forced]

        labels = {"idle": "待机", "walk": "行走", "run": "奔跑", "attack": "攻击", "jump": "跳跃"}
        sources_by_view = {}
        for view in sorted({views_by_action[action] for action in needed_actions}):
            source = service._asset_render(asset, view=view)
            if source:
                sources_by_view[view] = source
                continue
            action_names = "、".join(
                labels.get(action, action)
                for action, action_view in views_by_action.items()
                if action_view == view
            )
            if view == "side":
                detail = "侧视动作（{}）缺少侧视源图——先在「设计三视图」生成侧视图".format(
                    action_names
                )
            else:
                detail = "正面动作（{}）缺少可用 AI 原画，无法生成动画".format(action_names)
            raise HTTPException(status_code=409, detail=detail)

        facing_by_view = {
            "side": _side_source_facing(asset),
        } if "side" in sources_by_view else {}
        batch_id = service.start_action_batch(
            asset.get("id"),
            sources_by_view,
            settings,
            actions=actions,
            enhance_context=_enhance_context_for(asset),
            views_by_action=views_by_action,
            force_actions=force_actions,
            facing_by_view=facing_by_view,
        )
        return {"batch_id": batch_id, "snapshot": service.action_batch_snapshot(batch_id)}

    @router.get("/animation/matrix")
    def animation_matrix(asset_id: str | None = None):
        """动作×视角矩阵：每个 (动作, 视角) 的最新交付状态（成功/质检异常/
        缺失）与运行中批次，供「仅补缺失 / 仅重试失败」。"""

        from studio.backend.animation_service.service import AnimationService

        asset = _resolve_asset(runtime, asset_id) if asset_id else None
        resolved_id = (asset or {}).get("id") or asset_id
        return AnimationService(ANIMATION_DIR).action_matrix(resolved_id)

    @router.get("/animation/batch-actions/{batch_id}")
    def action_batch_status(batch_id: str):
        from studio.backend.animation_service.service import AnimationService

        snapshot = AnimationService(ANIMATION_DIR).action_batch_snapshot(batch_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown batch")
        return snapshot

    @router.get("/animation/rig-check")
    def animation_rig_check(asset_id: str | None = None):
        """骨骼绑定体检：检测角色头身比，Q 版角色全身骨骼会系统性错位，
        建议改用 AI 视频驱动（P1 生成质量）。"""

        from artgen.rig import build_rig
        from studio.backend.animation_service.service import AnimationService

        service = AnimationService(ANIMATION_DIR)
        asset = _resolve_asset(runtime, asset_id)
        source = service._asset_render(asset) if asset is not None else None
        if not source:
            raise HTTPException(status_code=409, detail="没有可用源图，无法评估骨骼绑定")
        rig = build_rig(source, 384)
        chibi = rig.get("proportion") == "chibi"
        return {
            "proportion": rig.get("proportion"),
            "head_ratio": rig.get("head_ratio"),
            "head_height": rig.get("head_height"),
            "confidence": rig.get("confidence"),
            "recommendation": "video" if chibi else "skeletal",
            "message": (
                "检测到 Q 版 / 大头比例（头宽≈躯干宽）。比例带骨骼对这类角色会系统性错位，"
                "建议改用「AI 视频驱动」生成动作，效果会好很多。"
                if chibi
                else "身体比例适合全身骨骼绑定。"
            ),
        }

    def _chat_once(settings: dict, prompt: str) -> str:
        """单轮对话模型调用（OpenAI 兼容），返回纯文本。"""

        import httpx as _httpx

        base_url = (settings.get("base_url") or "").rstrip("/")
        api_key = settings.get("api_key")
        model = settings.get("chat_model") or settings.get("model")
        if not base_url or not api_key or not model:
            raise RuntimeError("对话模型未配置完整")
        response = _httpx.post(
            base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
            },
            timeout=float(settings.get("timeout", 60)),
        )
        response.raise_for_status()
        from studio.backend.model_service.usage import record_usage

        record_usage("chat", model)
        return response.json()["choices"][0]["message"]["content"].strip()

    @router.post("/animation/sequence")
    def create_sequence_animation(request: SequenceRequest):
        """标准序列帧工作流：导入的帧图按给定顺序合成为循环动画。"""
        from studio.backend.animation_service.service import AnimationService

        if len(request.frames) < 2:
            raise HTTPException(status_code=422, detail="至少导入 2 张序列帧")
        if len(request.frames) > 60:
            raise HTTPException(status_code=422, detail="序列帧最多 60 张")
        frames = []
        for index, data in enumerate(request.frames):
            try:
                frames.append(base64.b64decode(data.split(",")[-1]))
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail=f"第 {index + 1} 帧不是合法的 base64")
        service = AnimationService(ANIMATION_DIR)
        try:
            return service.create_sequence(frames=frames, fps=request.fps, size=request.size)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

    @router.post("/animation/analyze")
    def analyze_animation_source(request: AnalyzeRequest):
        from studio.backend.animation_service.service import analyze_only

        try:
            image_bytes = base64.b64decode(request.image.split(",")[-1])
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="image 不是合法的 base64")
        try:
            return analyze_only(image_bytes)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

    @router.get("/animation/{name:path}")
    def get_animation_file(name: str):
        from studio.backend import artifact_store
        from studio.backend.animation_service.service import AnimationService

        path = AnimationService(ANIMATION_DIR).path(name)
        if path is None:
            # 本地缺失时回源对象存储（重新部署后动画帧同样需要可恢复）
            path = artifact_store.ensure_local("data/animation/" + name.replace("\\", "/"))
        if path is None:
            raise HTTPException(status_code=404, detail="unknown animation file")
        if name.endswith(".gif"):
            media = "image/gif"
        elif name.endswith(".png"):
            media = "image/png"
        elif name.endswith(".mp4"):
            media = "video/mp4"
        else:
            media = "application/octet-stream"
        response = FileResponse(path, media_type=media)
        if name.startswith("play_cache/"):
            # 试玩条带以内容哈希命名（同名=同内容），可长期缓存：
            # 重访/切换动作命中浏览器缓存时零网络请求
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    # ------------------------------------------------------------------
    # P1-A 资产版本树 / 差异对比 / 一键回滚
    # ------------------------------------------------------------------

    @router.get("/versions/groups")
    def version_groups():
        from studio.backend.version_service import VersionService

        return {"groups": VersionService.groups(runtime.history)}

    @router.get("/versions/tree")
    def version_tree(name: str):
        from studio.backend.version_service import VersionService

        tree = VersionService.tree(runtime.history, name)
        if not tree["versions"]:
            raise HTTPException(status_code=404, detail="unknown character name")
        return tree

    @router.get("/versions/diff")
    def version_diff(name: str, a: int, b: int):
        from studio.backend.version_service import VersionService

        tree = VersionService.tree(runtime.history, name)
        result = VersionService.diff(tree, a, b)
        if result is None:
            raise HTTPException(status_code=404, detail="version not found")
        return result

    @router.post("/versions/rollback")
    def rollback_versions(request: RollbackRequest):
        """一键回滚：把选中的历史版本快照恢复为当前资产（批量=按顺序恢复，
        最后一个成为"当前版本"），并写入回滚审计日志。"""

        from studio.backend.version_service import VersionService

        if not request.record_ids:
            raise HTTPException(status_code=422, detail="record_ids 不能为空")
        entries = []
        restored_asset = None
        for record_id in request.record_ids:
            record = runtime.history.get(record_id)
            asset = (record or {}).get("asset")
            if not isinstance(asset, dict) or not asset.get("id"):
                entries.append(
                    {"record_id": record_id, "ok": False, "error": "record has no asset snapshot"}
                )
                continue
            restored = dict(asset)
            runtime.assets.save(restored)
            restored_asset = restored
            tree = VersionService.tree(runtime.history, record.get("name") or "未命名资产")
            version_no = next(
                (v["version_no"] for v in tree["versions"] if v["record_id"] == record_id), None
            )
            entries.append(
                {
                    "ok": True,
                    "record_id": record_id,
                    "asset_id": restored.get("id"),
                    "name": record.get("name"),
                    "version_no": version_no,
                }
            )
        ok_entries = [entry for entry in entries if entry.get("ok")]
        if not ok_entries:
            raise HTTPException(status_code=404, detail="没有可恢复的资产快照")
        audit = VersionService().log_rollback(ok_entries)
        return {
            "status": "ok",
            "restored": len(ok_entries),
            "entries": entries,
            "rollback_id": audit["id"],
            "current_asset_id": restored_asset.get("id"),
        }

    @router.get("/versions/rollbacks")
    def rollback_history():
        from studio.backend.version_service import VersionService

        return {"rollbacks": VersionService().rollback_log()}

    @router.post("/versions/tag")
    def tag_version(request: VersionTagRequest):
        """版本定稿标记（协作）：approved / needs-work / none。"""

        if request.tag not in ("approved", "needs-work", "none"):
            raise HTTPException(status_code=422, detail="tag 仅支持 approved / needs-work / none")
        ok = runtime.history.tag_record(
            request.record_id,
            "review_tag",
            None if request.tag == "none" else request.tag,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="unknown record")
        return {"status": "ok", "record_id": request.record_id, "tag": request.tag}

    @router.post("/assets/review")
    def review_asset(request: ReviewRequest):
        """人工审核（体验）：生成结果通过 / 重做，写回资产与历史。"""

        asset = _resolve_asset(runtime, request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        review = {
            "approved": request.approved,
            "note": request.note,
            "at": time.time(),
        }
        asset["review"] = review
        saved = dict(asset)
        runtime.assets.save(saved)
        runtime.history.patch_asset(request.asset_id, {"review": review})
        return {"status": "ok", "asset_id": saved.get("id"), "review": review}

    @router.post("/design/cutout")
    def cutout_asset(request: dict):
        """一键透明底（功能）：AI 分割抠出角色，导出透明底立绘 PNG。"""

        from studio.backend.model_service.service import GENERATED_DIR

        asset = _resolve_asset(runtime, (request or {}).get("asset_id") or "")
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="透明底需要自定义模型（AI 主体分割）")

        from io import BytesIO

        from PIL import Image as PILImage

        from artgen.sourceanim import _fit
        from studio.backend.animation_service.service import (
            AnimationService,
            ai_segment_subject,
        )

        source_bytes = AnimationService(ANIMATION_DIR)._asset_render(asset)
        if not source_bytes:
            raise HTTPException(status_code=409, detail="该资产没有可用的源图")
        size = 512
        mask = ai_segment_subject(source_bytes, size, settings, deadline=time.time() + 150.0)
        if mask is None:
            raise HTTPException(status_code=502, detail="主体分割失败，请重试")
        original = _fit(PILImage.open(BytesIO(source_bytes)), size)
        cutout = original.copy()
        cutout.putalpha(mask)
        name = "cutout_{:.0f}.png".format(time.time() * 1000)
        buffer = BytesIO()
        cutout.save(buffer, "PNG")
        with open(os.path.join(GENERATED_DIR, name), "wb") as handle:
            handle.write(buffer.getvalue())

        url = "/api/generated/" + name
        asset["cutout_png"] = url
        saved = dict(asset)
        runtime.assets.save(saved)
        runtime.history.patch_asset(saved.get("id"), {"cutout_png": url})
        return {"status": "ok", "cutout_png": url, "asset_id": saved.get("id")}

    # ------------------------------------------------------------------
    # OneTake 发布展示视频（External Creative Capability）
    # ------------------------------------------------------------------

    def _showcase_service():
        from studio.backend.model_service.service import GENERATED_DIR
        from studio.backend.showcase_service.service import ShowcaseService

        return ShowcaseService(
            os.path.join(GENERATED_DIR, "showcase"),
            ANIMATION_DIR,
            # 配音链路：Key 池（TTS 额度轮换）+ 对话模型润色（失败回落模板）
            settings_provider=lambda: runtime.model_settings.effective(),
            chat_fn=lambda prompt: _chat_once(runtime.model_settings.effective(), prompt),
        )

    @router.post("/showcase", status_code=202)
    def start_showcase(request: dict):
        """CreativeAsset → OneTake 发布片（一镜到底）。素材缺失 409 + 中文
        可读提示（不做静默兜底）；渲染环境缺失 409 + 修复指引。"""

        from fastapi import HTTPException

        from adapters.onetake import render_client

        asset = _resolve_asset(runtime, str(request.get("asset_id") or ""))
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        if not render_client.playwright_available():
            raise HTTPException(
                status_code=409,
                detail="演示机未安装 playwright/chromium：先执行 `python -m pip install playwright` "
                "与 `python -m playwright install chromium`",
            )
        service = _showcase_service()
        job_id = service.start_showcase(asset, duration=float(request.get("duration") or 15.0))
        return {"job_id": job_id, "snapshot": service.snapshot(job_id)}

    @router.get("/showcase/{job_id}")
    def showcase_status(job_id: str):
        from fastapi import HTTPException

        snapshot = _showcase_service().snapshot(job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown showcase job")
        return snapshot

    @router.get("/showcase/{job_id}/file/{rel_path:path}")
    def showcase_file(job_id: str, rel_path: str):
        """job 产物伺服（mp4/poster/comp 预览；目录穿越防护同 AnimationService.path）。"""

        from fastapi import HTTPException
        from fastapi.responses import FileResponse

        path = _showcase_service().file(job_id, rel_path)
        if path is None:
            raise HTTPException(status_code=404, detail="not found")
        media = "text/html" if path.endswith(".html") else "application/octet-stream"
        if path.endswith(".png"):
            media = "image/png"
        elif path.endswith(".mp4"):
            media = "video/mp4"
        return FileResponse(path, media_type=media)


    @router.get("/playtest/previews")
    def playtest_previews(
        asset_id: str | None = None, actions: str | None = None
    ):
        """试玩舞台动作预览。

        有资产时绑定「当前角色的真实源图」：Character Rig 提取 → 分区变形
        （与动画工作台骨骼模式同一条链路），不同角色得到各自的外观与动作；
        没有资产（或源图解析失败）时才回退默认演示角色。条带图统一裁掉
        空白边并返回真实帧尺寸，前端据此按角色实际比例摆放、脚底贴地。

        V2 渐进式加载参数（缺省=旧行为，完全向后兼容）：
        - actions：逗号分隔的动作过滤（?actions=idle,walk 只渲染这两个
          动作的条带），空/全部非法时回退试玩默认四动作。
        rig/分割 mask 按 source_hash 进程内缓存，分批请求不重复执行
        昂贵准备。
        """

        import hashlib

        from PIL import Image as PILImage

        from artgen import asset_params
        from artgen.anim import render_action_frames

        PLAYTEST_SIZE = 256
        # 16 帧 @16fps：1s 完整循环、16 个离散步——8 帧 @10fps 的步进感是
        # 试玩区"卡顿"的主要来源；渲染尺寸 96→256 修复细特征在最近邻放大
        # 下的块状化（角尖悬浮成"虫角"、手臂细断、描边破碎）
        PLAYTEST_FRAMES = 16
        PLAYTEST_FPS = 16
        # 仅使用显式传入的 asset：没有 asset_id 时一律默认演示角色，
        # 不做 latest 回退（避免历史资产劫持试玩区）
        asset = _resolve_asset(runtime, asset_id) if asset_id else None

        requested = actions  # ?actions=idle,walk（逗号分隔过滤；None=默认全集）
        playtest_actions = ["idle", "walk", "run", "jump"]
        actions = list(playtest_actions)
        if requested is not None:
            wanted = {part.strip() for part in requested.split(",") if part.strip()}
            # attack 仍可被 PVE 战斗舞台显式请求；普通试玩默认与前端动作坞
            # 均只提供四个基础动作。旧前端若缓存了 attack 请求也不会把冗余
            # 动作带回普通试玩舞台。
            requestable_actions = (
                [*playtest_actions, "attack"]
                if isinstance(asset, dict) and asset.get("pve_enemy")
                else playtest_actions
            )
            actions = [name for name in requestable_actions if name in wanted] or list(
                playtest_actions
            )

        def _source_is_transparent(data: bytes) -> bool:
            import io as _io

            try:
                with PILImage.open(_io.BytesIO(data)) as handle:
                    if handle.mode in ("RGBA", "LA", "PA"):
                        return handle.getchannel("A").getextrema()[0] < 200
            except Exception:
                pass
            return False

        cache_dir = os.path.join(ANIMATION_DIR, "play_cache")
        os.makedirs(cache_dir, exist_ok=True)

        from studio.backend import artifact_store

        def _ensure_cached(name: str) -> str:
            """重启后容器盘被清空：条带缓存缺失时按需回源，避免整条重渲染。"""
            path = os.path.join(cache_dir, name)
            if not os.path.isfile(path):
                artifact_store.ensure_local("data/animation/play_cache/" + name)
            return path

        def _ensure_frame(name: str) -> str:
            path = os.path.join(ANIMATION_DIR, name)
            if not os.path.isfile(path):
                artifact_store.ensure_local("data/animation/" + name)
            return path

        # v5：帧粘连修复（分区独占所有权：父段裁到膝/肘 + 裆部立柱只填洞）
        # v6：比例修复（R1 封闭洞回收限主体下半部 + 双脚分离关节点 + 膝线
        # 剖面检测 + 腿带中缝/顶部按真实双脚收窄）——渲染语义再变，旧条带作废
        # v7：matting 精修（sourceanim.refine_edge_alpha 白底 alpha 反解，
        # 边界带像素色与 alpha 均变化）——非透明源条带旧缓存作废
        # v8：条带裁切起点对齐帧边界（旧条带每帧窗口偏进前一帧，
        # 播放时胸口/颈部会粘上邻帧残段）——所有旧条带作废
        # v9：内置动作改整身形变（不再切分身体分区）——分区骨架在 Q 版
        # 角色上会在颈胸留下横向撕裂，旧 rigged 条带全部作废
        # v10：整身形变幅度调优（步频/挤压/冲刺更可读）——v9 条带作废
        # v11：整身形变（sprite）接入 AI segment_mask 背景透明化——非透明源的
        # 复杂/米色背景此前洪泛兜不住、帧上残留底色，旧 sprite 条带作废
        PLAYTEST_CACHE_VERSION = 11

        def _digest(engine_name: str, seed: str, action: str) -> str:
            return hashlib.sha1(
                "{}|{}|{}|{}|{}".format(
                    PLAYTEST_CACHE_VERSION, engine_name, PLAYTEST_SIZE, seed, action
                ).encode()
            ).hexdigest()[:10]

        def _procedural_seed() -> str:
            return str(
                ((asset_params(asset) or {}).get("seed") if asset is not None else None)
                or "playtest"
            )

        # 第一步：只解析源图 + 算哈希。全部条带命中缓存时到此为止，
        # 不做 AI 分割、不建骨架（缓存快路径 ~0ms）
        source = None
        source_hash = None
        if asset is not None:
            from studio.backend.animation_service.service import AnimationService

            source = AnimationService(ANIMATION_DIR)._asset_render(asset)
            if source is None:
                # 重启后无本地文件的历史资产：退回资产正面立绘（与工作台
                # 展示同一渲染），保证试玩的仍是这个角色而不是模板小人
                from artgen import render_asset_view

                try:
                    source = render_asset_view(asset, "front", PLAYTEST_SIZE * 2)
                except Exception:
                    source = None
            if source is not None:
                source_hash = hashlib.sha1(source).hexdigest()[:12]

        engine = "sprite" if source_hash else "procedural"
        seed_key = "sprite-{}".format(source_hash) if source_hash else _procedural_seed()

        def pack_strip(frames: list) -> "PILImage.Image":
            frame_w, frame_h = frames[0][0], frames[0][1]
            sheet = PILImage.new("RGBA", (frame_w * len(frames), frame_h), (0, 0, 0, 0))
            for index, (w, h, rgba) in enumerate(frames):
                sheet.paste(PILImage.frombytes("RGBA", (w, h), bytes(rgba)), (index * frame_w, 0))
            # 裁掉整条空白边：帧紧贴角色本体，比例即角色真实比例，
            # 帧底 = 脚底线（跳跃/抬脚帧自然留出离地空间）
            box = sheet.getbbox()
            if box:
                pad = 2
                x0, y0, x1, y1 = box
                # 帧宽对齐：裁切起点必须落在帧边界上，否则第一帧取景偏移，
                # 前端按「总宽/帧数」裁切时每帧都会带一段邻帧残影
                x0 = (max(0, x0 - pad) // frame_w) * frame_w
                y0 = max(0, y0 - pad)
                y1 = min(sheet.height, y1 + pad)
                x1 = min(sheet.width, x0 + frame_w * len(frames))
                sheet = sheet.crop((x0, y0, x1, y1))
            return sheet

        expected_views = dict(PLAYTEST_VIEW_BY_ACTION)
        if isinstance(asset, dict) and asset.get("pve_enemy"):
            # PVE enemy forge generates its compact action set from the front
            # source; reuse those AI strips instead of rebuilding procedural
            # walk/run bands on first play.
            for action in ("walk", "run", "jump"):
                expected_views[action] = "front"
            if asset.get("pve_action_view") == "side":
                for action in ("idle", "walk", "attack"):
                    expected_views[action] = "side"
            for action, view in (asset.get("pve_action_views") or {}).items():
                if action in ("idle", "walk", "attack") and view in ("front", "side"):
                    expected_views[action] = view

        from studio.backend.animation_service.service import collect_ai_strips

        available_ai_strips = (
            collect_ai_strips(
                ANIMATION_DIR,
                asset_id,
                actions,
                view_by_action=expected_views,
            )
            if asset_id
            else {}
        )
        from studio.backend.animation_service.playtest_strip import (
            cache_names,
            schedule_strip,
        )

        def _cached_ai_strip(meta):
            """缓存命中（含对象存储回源）返回 (路径, 帧数)，否则 None。"""
            for name, count in cache_names(meta):
                path = _ensure_cached(name)
                if os.path.isfile(path):
                    return path, count
            return None

        def _procedural_name(action: str) -> str:
            return "play_{}_{}.png".format(action, _digest(engine, seed_key, action))

        def _needs_procedural(action: str) -> bool:
            """AI 条带尚未打包成缓存时也要准备一条程序化兜底，避免请求
            同步等待几十秒的抠图；后台打包完成后下次刷新自动切回 AI。"""
            if os.path.isfile(_ensure_cached(_procedural_name(action))):
                return False
            meta = available_ai_strips.get(action)
            if meta is not None and _cached_ai_strip(meta) is not None:
                return False
            return True

        pending = [action for action in actions if _needs_procedural(action)]

        # AI 动画帧收集（只读磁盘，需在骨架准备前完成）
        ai_strips: dict[str, dict] = {}
        if asset_id:
            ai_strips = collect_ai_strips(
                ANIMATION_DIR,
                asset_id,
                actions,
                view_by_action=expected_views,
            )

        # 第二步：真的需要渲染时才做昂贵准备 —— 一次 AI 主体分割（五动作
        # 共享同一 mask），一次骨架提取；复杂背景由分割解决，经典洪泛兜底。
        # rig/mask 按 source_hash 命中进程内缓存（V2 分批请求第二批不再
        # 重复执行 AI 分割与骨架提取）
        rig = None
        segment_mask = None
        if source is not None and pending:
            cached = _PLAYTEST_RIG_CACHE.get(source_hash) if source_hash else None
            if cached is not None:
                rig, segment_mask = cached
            else:
                if not _source_is_transparent(source):
                    settings = runtime.model_settings.effective()
                    if settings.get("enabled") and settings.get("api_key"):
                        try:
                            from studio.backend.animation_service.service import (
                                ai_segment_subject,
                            )

                            segment_mask = ai_segment_subject(
                                source, PLAYTEST_SIZE, settings, deadline=time.time() + 10.0
                            )
                        except Exception:
                            segment_mask = None
                try:
                    from artgen.rig import build_rig

                    rig = build_rig(source, PLAYTEST_SIZE, segment_mask=segment_mask)
                except Exception:
                    rig = None
                if source_hash and rig is not None:
                    _PLAYTEST_RIG_CACHE[source_hash] = (rig, segment_mask)
                    if len(_PLAYTEST_RIG_CACHE) > 8:
                        _PLAYTEST_RIG_CACHE.pop(next(iter(_PLAYTEST_RIG_CACHE)))

        if source is not None and pending:
            # 内置动作走整身形变：完整角色只做位移/倾斜/挤压，帧内不存在
            # 分区接缝（分区 rig 在 Q 版角色颈胸会撕裂），帧间用正弦相位衔接
            from artgen.riganim import animate_sprite

            def _render(action: str):
                return animate_sprite(
                    source, action, PLAYTEST_FRAMES, PLAYTEST_SIZE, segment_mask=segment_mask
                )[0]

            try:
                from concurrent.futures import ThreadPoolExecutor

                # 有界并发：动作渲染互不依赖，共享只读 rig
                with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
                    rendered = dict(zip(pending, list(pool.map(_render, pending))))
            except Exception:
                # 任何动作失败都整体回退程序化演示角色，
                # 避免同一舞台混搭两种外观
                rendered = None
            if rendered is None:
                engine = "procedural"
                rig = None
                seed_key = _procedural_seed()
                pending = actions
            else:
                for action, frames in rendered.items():
                    pack_strip(frames).save(
                        os.path.join(
                            cache_dir,
                            "play_{}_{}.png".format(action, _digest(engine, seed_key, action)),
                        ),
                        "PNG",
                    )
                if rig is not None:
                    # rig 摘要落盘：缓存快路径跳过骨架构建时仍能返回角色信息
                    meta = {
                        "proportion": rig.get("proportion", "normal"),
                        "confidence": rig.get("confidence"),
                        "head_ratio": rig.get("head_ratio"),
                        "source_hash": rig.get("source_hash"),
                    }
                    with open(
                        os.path.join(cache_dir, "play_meta_{}.json".format(source_hash)),
                        "w",
                        encoding="utf-8",
                    ) as handle:
                        handle.write(json.dumps(meta, ensure_ascii=False))
                pending = []

        if pending:
            # 程序化回退：无资产 / 源图解析失败 / 骨骼渲染失败。
            # 与 rig 路径同尺寸渲染——渲染器按 512 设计稿等比缩放，
            # 96px 时细特征低于 1 像素消失（历史上"bug 展品"的根因）
            params = (
                asset_params(asset) if asset is not None else {"palette": None, "seed": "playtest"}
            )
            for action in pending:
                frames = render_action_frames(
                    params, action, PLAYTEST_FRAMES, PLAYTEST_SIZE, None
                )
                pack_strip(frames).save(
                    os.path.join(
                        cache_dir,
                        "play_{}_{}.png".format(action, _digest(engine, seed_key, action)),
                    ),
                    "PNG",
                )

        # ── AI 动画帧优先（用户授权 API 路线）：该资产+动作已生成过 AI
        # 视频驱动动画时，用其真实帧拼条带；未生成的动作回退 rigged/
        # procedural 渲染。收集已在骨架准备前完成（ai_strips）。

        def _pack_ai_strip(meta, label: str | None = None):
            """AI 动画条带只读缓存：命中即刻返回；未命中转后台打包并返回
            None，由路由先用程序化/骨骼条带兜底，绝不把几十秒的抠图塞进
            托管平台的 60s 请求窗口（实测 32 帧会直接超时断连）。"""

            cached = _cached_ai_strip(meta)
            if cached is None:
                schedule_strip(
                    meta,
                    ANIMATION_DIR,
                    cache_dir,
                    ensure_frame=lambda name: _ensure_frame(name),
                )
                return None
            out_path, used_frames = cached
            effective_facing = meta.get("source_facing")
            if meta.get("view") == "side" and effective_facing not in ("left", "right"):
                # 本字段上线前的侧视动作均由旧“面朝左”prompt 生成；即使
                # 之后重做了三视图，也不能用新朝向去解释旧动作。
                effective_facing = "left"
            if meta.get("view") != "side":
                effective_facing = None
            with PILImage.open(out_path) as handle:
                strip_w, strip_h = handle.size
            return {
                "url": "/api/animation/play_cache/" + os.path.basename(out_path),
                "frames": used_frames,
                # width 必须是单帧宽（不是整条宽度）：前端与检查报告都按它换算
                "width": max(1, strip_w // max(1, used_frames)),
                "height": strip_h,
                "fps": meta.get("fps", 12),
                "engine": "ai-video",
                # 实际视角/源图朝向（试玩 Canvas 据此归一化左右镜像）
                "view": meta.get("view"),
                **({"facing": effective_facing} if effective_facing else {}),
            }

        previews: dict[str, str] = {}
        strips: dict[str, dict] = {}
        deferred_ai: list[str] = []
        side_facing = _side_source_facing(asset)

        def _facing_for(action: str) -> str | None:
            return side_facing if PLAYTEST_VIEW_BY_ACTION.get(action) == "side" else None

        for action in actions:
            ai_meta = ai_strips.get(action)
            if ai_meta is not None:
                packed = _pack_ai_strip(ai_meta)
                if packed:
                    previews[action] = packed["url"]
                    strips[action] = packed
                    continue
                # 后台正在打包：本轮先用兜底条带，前端轮询后再切回 AI
                deferred_ai.append(action)
            strip_path = _ensure_cached(_procedural_name(action))
            with PILImage.open(strip_path) as handle:
                strip_w, strip_h = handle.size
            url = "/api/animation/play_cache/" + os.path.basename(strip_path)
            previews[action] = url
            strips[action] = {
                "url": url,
                "frames": PLAYTEST_FRAMES,
                "fps": PLAYTEST_FPS,
                "width": max(1, strip_w // PLAYTEST_FRAMES),
                "height": strip_h,
                "engine": engine,
                # 回退条带的视角/源图朝向（PVE attack 不在默认策略表内为 None）
                "view": PLAYTEST_VIEW_BY_ACTION.get(action),
                **({"facing": _facing_for(action)} if _facing_for(action) else {}),
            }

        character = None
        if source_hash and engine in ("rigged", "sprite"):
            meta_path = os.path.join(cache_dir, "play_meta_{}.json".format(source_hash))
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as handle:
                        character = json.load(handle)
                except Exception:
                    character = None
            elif rig is not None:
                character = {
                    "proportion": rig.get("proportion", "normal"),
                    "confidence": rig.get("confidence"),
                    "head_ratio": rig.get("head_ratio"),
                    "source_hash": rig.get("source_hash"),
                }
        return {
            "previews": previews,
            "actions": actions,
            "strips": strips,
            "fps": PLAYTEST_FPS,
            "source": engine,
            "character": character,
            # AI 条带正在后台打包：前端据此短暂轮询，切回 AI 帧
            "deferred_ai": deferred_ai,
        }

    # ------------------------------------------------------------------
    # 试玩舞台 3D POC-0
    # ------------------------------------------------------------------

    @router.get("/playtest/3d")
    def playtest_3d(asset_id: str | None = None):
        """3D 试玩清单。

        没有 ``asset_id`` 时走离网固定夹具（GLB + manifest 随仓库提交），
        用于验收「真实 GLB 加载 → AnimationMixer 播放」链路；有 ``asset_id``
        时从该资产的 ``extensions.cloud_backends.mesh`` 槽位解析 GLB 地址。
        """

        if not asset_id:
            return _playtest3d_fixture_manifest()
        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            return _playtest3d_error_manifest(asset_id, "asset_not_found", "/playtest")
        from adapters.cloud_backends.contracts import extension_v1 as contract

        mesh = (contract.read_extension(asset) or {}).get("mesh")
        return _playtest3d_manifest_from_mesh(asset_id, mesh)

    @router.get("/playtest/3d/fixture.glb")
    def playtest_3d_fixture_glb():
        """伺服固定 GLB 夹具（离网验收用，不进 CreativeAsset 主协议）。"""

        path = os.path.join(_PLAYTEST3D_FIXTURE_DIR, "character.glb")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="3D 夹具缺失")
        return FileResponse(path, media_type="model/gltf-binary", filename="character.glb")

    @router.post("/open-folder")
    def open_folder(request: OpenFolderRequest):
        """在资源管理器中打开生成产物目录（白名单：generated/animation/
        exports）。仅本机后端可用——浏览器页面无权直接唤起系统文件管理器。"""

        import subprocess
        import sys

        from studio.backend.model_service.service import GENERATED_DIR

        targets = {
            "generated": GENERATED_DIR,
            "animation": ANIMATION_DIR,
            "exports": EXPORTS_DIR,
        }
        folder = targets.get(request.target)
        if not folder or not os.path.isdir(folder):
            raise HTTPException(status_code=404, detail="unknown folder")
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # noqa: S606 - 本机受控白名单目录
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            raise HTTPException(status_code=500, detail="无法打开文件夹：{}".format(exc))
        return {"status": "ok", "target": request.target, "path": folder}

    @router.get("/health")
    def health():
        from studio.backend import artifact_store

        return {
            "status": "ok",
            "service": "creativeforge-studio",
            # 构建过期自检：dist 落后于 src 时前端显示「请重新构建并强刷」角标
            "frontend_stale": _frontend_build_stale(),
            # 产物对象存储是否就绪（托管容器无持久盘，未就绪时重新部署即丢产物）
            "artifact_store": artifact_store.configured(),
        }

    # ── 对象存储：API 配置（CRUD + 设默认 + 连通性测试） ────────────────────
    # 凭证本地加密存储、界面脱敏展示、禁止明文回显与明文写入日志。

    class StorageConfigRequest(BaseModel):
        name: str
        provider: str
        access_key: str | None = None  # 空串/None 表示编辑时保持原值
        secret_key: str | None = None
        region: str | None = None
        bucket: str | None = None
        endpoint: str | None = None
        is_default: bool | None = None

    class StorageTestRequest(BaseModel):
        config_id: str | None = None
        name: str | None = None
        provider: str | None = None
        access_key: str | None = None
        secret_key: str | None = None
        region: str | None = None
        bucket: str | None = None
        endpoint: str | None = None

    class PresignRequest(BaseModel):
        key: str
        expires: int = 3600
        config_id: str | None = None

    class MultipartStartRequest(BaseModel):
        key: str
        total_size: int
        part_size: int | None = None
        content_type: str = "application/octet-stream"
        config_id: str | None = None

    def _storage():
        from studio.backend.storage_service import get_storage_manager

        return get_storage_manager()

    @router.get("/storage/configs")
    def list_storage_configs():
        manager = _storage()
        return {
            "configs": manager.store.list_public(),
            "presets": _storage_presets_view(),
            "default_id": manager.default_config_id(),
        }

    @router.post("/storage/configs", status_code=201)
    def create_storage_config(request: StorageConfigRequest):
        try:
            return _storage().store.create(request.model_dump())
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.put("/storage/configs/{config_id}")
    def update_storage_config(config_id: str, request: StorageConfigRequest):
        try:
            return _storage().store.update(config_id, request.model_dump())
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete("/storage/configs/{config_id}")
    def delete_storage_config(config_id: str):
        try:
            return _storage().store.delete(config_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/configs/{config_id}/default")
    def set_default_storage_config(config_id: str):
        try:
            return _storage().store.set_default(config_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/configs/test")
    def test_storage_config(request: StorageTestRequest):
        payload = None
        if any(
            request.model_dump().get(k)
            for k in (
                "name",
                "provider",
                "region",
                "bucket",
                "endpoint",
                "access_key",
                "secret_key",
            )
        ):
            payload = request.model_dump()
        return _storage().test_config(config_id=request.config_id, payload=payload)

    # ── 对象存储：文件操作（统一接口：列举 / 上传 / 下载 / 删除 / 临时链接） ──

    @router.get("/storage/files")
    def list_storage_files(config_id: str | None = None, prefix: str = "", limit: int = 100):
        try:
            return {
                "objects": _storage().list(prefix, config_id=config_id, limit=limit),
                "config_id": config_id,
            }
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/files", status_code=201)
    async def upload_storage_file(
        file: "UploadFile" = File(...), key: str = Form(None), config_id: str | None = Form(None)
    ):
        data = await file.read()
        object_key = key or file.filename or f"upload/{file.filename}"
        try:
            return _storage().upload(
                data,
                object_key,
                config_id=config_id,
                content_type=file.content_type or "application/octet-stream",
            )
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/storage/files/{key:path}")
    def get_storage_file(key: str, config_id: str | None = None, download: bool = True):
        manager = _storage()
        try:
            data = manager.download(key, config_id=config_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{key.rsplit("/", 1)[-1]}"'},
        )

    @router.delete("/storage/files/{key:path}")
    def delete_storage_file(key: str, config_id: str | None = None):
        try:
            return _storage().delete(key, config_id=config_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/presign")
    def presign_storage_file(request: PresignRequest):
        try:
            return _storage().presign(
                request.key, config_id=request.config_id, expires=request.expires
            )
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    # ── 对象存储：大文件分片上传（断点续传 / 失败重试 / 超时控制） ──────────

    @router.post("/storage/multipart/start", status_code=201)
    def start_multipart(request: MultipartStartRequest):
        try:
            return _storage().multipart.start(
                request.config_id or _storage().default_config_id(),
                request.key,
                request.total_size,
                part_size=request.part_size or None,
                content_type=request.content_type,
            )
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/storage/multipart/{session_id}")
    def get_multipart_status(session_id: str):
        try:
            return _storage().multipart.status(session_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/storage/multipart/{session_id}/resume")
    def resume_multipart(session_id: str):
        try:
            return _storage().multipart.resume(session_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.put("/storage/multipart/{session_id}/{part_number}")
    async def upload_multipart_part(
        session_id: str, part_number: int, file: "UploadFile" = File(...)
    ):
        data = await file.read()
        try:
            return _storage().multipart.upload_part(session_id, part_number, data)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/multipart/{session_id}/complete")
    def complete_multipart(session_id: str):
        try:
            return _storage().multipart.complete(session_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/storage/multipart/{session_id}/abort")
    def abort_multipart(session_id: str):
        try:
            return _storage().multipart.abort(session_id)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router


def _storage_presets_view() -> dict:
    """厂商预设给前端填表用（不含任何凭证）。"""
    from studio.backend.storage_service.providers import PROVIDER_PRESETS

    return {
        key: {
            "id": value["id"],
            "label": value["label"],
            "addressing": value["addressing"],
            "regions": value["regions"],
            "endpoint_template": value["endpoint_template"],
            "credential_hint": value["credential_hint"],
        }
        for key, value in PROVIDER_PRESETS.items()
    }
