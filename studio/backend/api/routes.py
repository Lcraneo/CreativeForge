"""REST API for the Studio frontend."""

import base64
import json
import os
import re
import time

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
_PREVIEW_FRAME_CACHE = {}  # (source_hash, action, config, size) -> [png bytes]
ANIMATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "animation"
)


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


class PreviewFrameRequest(BaseModel):
    asset_id: str | None = None
    action: str = "walk"
    view: str = "front"
    phase: float = 0.0  # 0..1 动作循环内相位
    size: int = 384
    pose_config: dict | None = None
    skeletal: bool = False  # 骨骼模式：预览当前角色绑定的骨架动画
    image: str | None = None  # 可选上传源图（base64），优先于 asset_id


class PlanRequest(BaseModel):
    goal: str
    asset_id: str | None = None


class EnhanceRequest(BaseModel):
    goal: str
    overrides: dict | None = None


class CustomActionRequest(BaseModel):
    name: str
    action: str = "walk"
    view: str = "front"
    pose_config: dict


class SequenceRequest(BaseModel):
    frames: list[str]  # base64 PNG / JPEG frame images, in play order
    fps: int = 12
    size: int = 384


class AnalyzeRequest(BaseModel):
    image: str  # base64 source image


class ExportRequest(BaseModel):
    asset_id: str
    engine: str = "cocos"


class BatchExportRequest(BaseModel):
    asset_ids: list[str]
    engine: str = "cocos"


class BatchRequest(BaseModel):
    goal: str
    count: int = 4  # 4 / 9 / 12
    mode: str = "seed"  # seed = 多变体 / pose = 多姿势
    overrides: dict | None = None


class RollbackRequest(BaseModel):
    record_ids: list[str]


class PixelEditRequest(BaseModel):
    pixels: list  # [[hex|null]] 方形颜色矩阵
    palette: list[str] | None = None


class ReviewRequest(BaseModel):
    asset_id: str
    approved: bool
    note: str | None = None


class VersionTagRequest(BaseModel):
    record_id: str
    tag: str  # approved / needs-work / none


class RestyleRequest(BaseModel):
    asset_id: str
    style: str  # pixel / anime / ink


class ActionPackRequest(BaseModel):
    actions: list


class ActionTextRequest(BaseModel):
    text: str


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
    timeout: int | None = None
    api_key_pool_add: list[str] | None = None  # 备用 Key 追加（每项一把）
    api_key_pool: list[str] | None = None  # 整池覆盖（清空传 []）
    api_key_pool_remove: list[int] | None = None  # 按池内序号移除（UI 拿到的是脱敏回显）


def _localize_asset(asset):
    """把资产里指向 DashScope OSS 的临时远程 URL 改写为本地代理
    ``/api/generated/<file>``。

    远程结果链接有三重裂图风险：浏览器网络环境可能无法直连 OSS、
    防盗链/Referer 策略、24 小时签名过期。生成时图片均已下载落盘
    （GENERATED_DIR），本地代理同源且永久可达。"""

    if not isinstance(asset, dict):
        return asset

    from studio.backend.model_service.service import safe_generated_path

    def localized(meta):
        if isinstance(meta, dict) and meta.get("file"):
            name = os.path.basename(str(meta["file"]))
            if safe_generated_path(name):
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

    restyle = asset.get("restyle")
    if isinstance(restyle, dict):
        asset["restyle"] = localized(restyle)
    return asset


def _localize_history_record(record):
    """历史记录的顶层 image 与内嵌 asset 都做 URL 本地化。"""

    asset = record.get("asset")
    if isinstance(asset, dict):
        record["asset"] = _localize_asset(asset)
    image = record.get("image")
    if isinstance(image, dict) and image.get("file"):
        from studio.backend.model_service.service import safe_generated_path

        name = os.path.basename(str(image["file"]))
        if safe_generated_path(name):
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
            goal, overrides=request.overrides, turbo=request.turbo, asset=asset
        )
        return {
            "task_id": task_id,
            "status": "running",
            "stream_url": "/ws/tasks/{}/stream".format(task_id),
        }

    @router.post("/plan")
    def plan_task(request: PlanRequest):
        """Dynamic Creative Planner: goal -> capability plan (before running)."""
        from studio.backend.plan_service import build_plan

        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="goal is required")
        return build_plan(goal, request.asset_id)

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
        """Deterministic 2D character artwork (front/side/top view)."""
        from artgen import render_asset_view

        # 也从历史解析：重启后工作台仍会展示历史资产图，动画/预览共用此图
        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        bounded = max(64, min(1024, int(size)))
        return Response(
            content=render_asset_view(asset, view=view, size=bounded),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Image-Style": "2d",
                "X-Image-View": view,
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

        asset = runtime.assets.get(request.asset_id)
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

    @router.get("/benchmark")
    def benchmark_report():
        from benchmark.evaluation import EvaluationReport

        report = EvaluationReport().run()
        return report

    @router.get("/history")
    def list_history(
        engine: str = None,
        q: str = None,
        limit: int = 100,
    ):
        records = [
            _localize_history_record(record)
            for record in runtime.history.list(limit=limit, engine=engine, keyword=q)
        ]
        return {"records": records, "total": runtime.history.count()}

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
        from studio.backend.model_service.service import safe_generated_path

        path = safe_generated_path(name)
        if path is None:
            raise HTTPException(status_code=404, detail="unknown image")
        return FileResponse(path)

    @router.get("/design/style-templates")
    def list_style_templates():
        """风格提示词模板库：确定性风格条款（前端幂等拼接到提示词尾部，
        与对话增强互补的质量下限保障）。返回有序列表。"""

        from studio.backend.model_service.style_templates import STYLE_TEMPLATES

        return {
            "templates": [dict(id=key, **tpl) for key, tpl in STYLE_TEMPLATES.items()]
        }

    @router.post("/design/views")
    def generate_design_views(request: dict):
        """基于资产的 AI 原画生成侧视/背视图（qwen-image-edit，含相似度自检）。"""
        from studio.backend.model_service.service import generate_turnaround

        asset_id = request.get("asset_id") or ""
        asset = runtime.assets.get(asset_id)
        if asset is None:
            # runtime 已重启等场景：从落盘历史里找回资产
            for record in runtime.history.list(limit=100):
                candidate = record.get("asset")
                if isinstance(candidate, dict) and candidate.get("id") == asset_id:
                    asset = candidate
                    break
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        base = (asset.get("image") or {}).get("url") or (asset.get("source") or {}).get(
            "ai_image", {}
        ).get("url")
        if not base:
            raise HTTPException(
                status_code=409,
                detail="该资产没有 AI 原画，无法生成三视图（先在工作台用自定义模型生成）",
            )

        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="自定义模型未启用或缺少 API Key")

        views, failures = generate_turnaround(settings, base, front_image=asset.get("image"))
        if not (views.get("side") or views.get("back")):
            raise HTTPException(status_code=502, detail="；".join(failures) or "generation failed")

        asset["design_views"] = views
        runtime.assets.save(asset)
        runtime.history.patch_asset(asset_id, {"design_views": views})
        return views

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
            source = image_bytes or service._asset_render(asset)
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
                )
            except RuntimeError as error:
                raise HTTPException(status_code=502, detail=str(error))
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
                pose_config=request.pose_config,
                model_settings=runtime.model_settings.effective(),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

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
        已生成的自动跳过。返回 batch_id 供轮询。"""

        from studio.backend.animation_service.service import AnimationService

        asset = _resolve_asset(runtime, request.get("asset_id") or "")
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="AI 动画生成需要先启用自定义模型")
        source = AnimationService(ANIMATION_DIR)._asset_render(asset)
        if not source:
            raise HTTPException(status_code=409, detail="该资产没有可用的 AI 原画")

        service = AnimationService(ANIMATION_DIR)
        batch_id = service.start_action_batch(
            asset.get("id"), source, settings,
            actions=request.get("actions"),
            enhance_context=_enhance_context_for(asset),
        )
        return {"batch_id": batch_id, "snapshot": service.action_batch_snapshot(batch_id)}

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

    @router.post("/animation/custom-actions/enhance")
    def enhance_action_text(request: ActionTextRequest):
        """动作描述润色（P1 体验）：对话模型把口语化描述改写成专业、具体的
        动作说明。失败抛 502，由前端提示。"""

        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="自定义模型未启用，无法使用文案增强")
        text = (request.text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="text 不能为空")
        prompt = (
            "你是资深游戏动作设计指导。把下面这段用户写的角色动作描述润色成清晰、具体、"
            "专业的动作说明（80 字以内中文，只输出润色后的描述本身，不要任何解释、"
            "不要列表、不要引号）。保留用户描述的全部意图，补全缺失的动作细节"
            "（预备、发力、跟随、收势）。\n\n用户描述：" + text
        )
        try:
            polished = _chat_once(settings, prompt)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return {"text": polished}

    @router.post("/animation/custom-actions/interpret")
    def interpret_action_text(request: ActionTextRequest):
        """动作结构化解读（P1 体验）：对话模型把动作描述转成 pose_config 参数
        JSON，直接套用动作编辑器。解析失败回退安全默认值。"""

        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="自定义模型未启用，无法解读动作描述")
        text = (request.text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="text 不能为空")
        import json as _json

        prompt = (
            "你是游戏动画参数师。把用户的动作描述转换成 JSON（只输出 JSON 本体，"
            "不要 markdown 代码块、不要解释）。JSON 格式：\n"
            '{"label": "动作名，4字以内中文", '
            '"base_action": "idle/walk/run/attack/jump 之一（最接近的整体动作类型）", '
            '"view": "front 或 side（side=侧视横版步态，仅 walk/run 建议）", '
            '"pose_config": {"bob": 上下起伏0~2, "stride": 步幅0~2, "arm": 摆臂0~2, '
            '"lift": 抬脚0~2, "lean": 前倾角度-15~30, "lag": 手臂滞后0~1.2, "cycles": 循环周期0.25~3}}\n'
            "数值必须落在范围内。\n\n用户描述：" + text
        )
        try:
            raw = _chat_once(settings, prompt)
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("no JSON in model output")
            data = _json.loads(raw[start : end + 1])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="解读失败：{}".format(str(exc)[:120]))

        label = str(data.get("label") or text[:6])
        base_action = str(data.get("base_action") or "attack")
        if base_action not in ("idle", "walk", "run", "attack", "jump"):
            base_action = "attack"
        view = str(data.get("view") or "front")
        if view not in ("front", "side"):
            view = "front"

        raw_pose = data.get("pose_config") or {}

        def clamp(value, lo, hi, default):
            try:
                return max(lo, min(hi, float(value)))
            except (TypeError, ValueError):
                return default

        pose_config = {
            "bob": clamp(raw_pose.get("bob"), 0, 2, 1),
            "stride": clamp(raw_pose.get("stride"), 0, 2, 1),
            "arm": clamp(raw_pose.get("arm"), 0, 2, 1),
            "lift": clamp(raw_pose.get("lift"), 0, 2, 1),
            "lean": clamp(raw_pose.get("lean"), -15, 30, 0),
            "lag": clamp(raw_pose.get("lag"), 0, 1.2, 0.45),
            "cycles": clamp(raw_pose.get("cycles"), 0.25, 3, 1),
        }
        return {
            "label": label[:12],
            "base_action": base_action,
            "view": view,
            "pose_config": pose_config,
            "source_text": text,
        }

    @router.get("/animation/action-pack")
    def export_action_pack():
        """动作包导出（扩展性）：全部自定义动作打包为可分享 JSON。"""

        from studio.backend.animation_service.custom_actions import CustomActionStore

        store = CustomActionStore(ANIMATION_DIR + "/custom_actions.json")
        actions = store.list()
        return {
            "format": "creativeforge-action-pack/1",
            "count": len(actions),
            "actions": actions,
        }

    @router.post("/animation/action-pack")
    def import_action_pack(request: ActionPackRequest):
        """动作包导入：批量写入自定义动作（同名覆盖）。"""

        from studio.backend.animation_service.custom_actions import CustomActionStore

        store = CustomActionStore(ANIMATION_DIR + "/custom_actions.json")
        imported = 0
        errors = []
        for item in request.actions or []:
            try:
                if not isinstance(item, dict) or not item.get("name"):
                    raise ValueError("missing name")
                store.save(
                    {
                        "name": str(item["name"]),
                        "action": str(item.get("action") or "walk"),
                        "view": str(item.get("view") or "front"),
                        "pose_config": item.get("pose_config") or {},
                    }
                )
                imported += 1
            except Exception as error:  # noqa: BLE001
                errors.append(str(error)[:80])
        return {"status": "ok", "imported": imported, "errors": errors}

    @router.get("/animation/custom-actions")
    def list_custom_actions():
        from studio.backend.animation_service.custom_actions import CustomActionStore

        return {"actions": CustomActionStore(ANIMATION_DIR + "/custom_actions.json").list()}

    @router.post("/animation/custom-actions")
    def save_custom_action(request: CustomActionRequest):
        from studio.backend.animation_service.custom_actions import CustomActionStore

        try:
            saved = CustomActionStore(ANIMATION_DIR + "/custom_actions.json").save(
                request.model_dump()
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        return saved

    @router.delete("/animation/custom-actions/{name}")
    def delete_custom_action(name: str):
        from studio.backend.animation_service.custom_actions import CustomActionStore

        if not CustomActionStore(ANIMATION_DIR + "/custom_actions.json").delete(name):
            raise HTTPException(status_code=404, detail="unknown custom action")
        return {"status": "deleted"}

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
        from studio.backend.animation_service.service import AnimationService

        path = AnimationService(ANIMATION_DIR).path(name)
        if path is None:
            raise HTTPException(status_code=404, detail="unknown animation file")
        if name.endswith(".gif"):
            media = "image/gif"
        elif name.endswith(".png"):
            media = "image/png"
        else:
            media = "application/octet-stream"
        return FileResponse(path, media_type=media)

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

    @router.post("/design/restyle")
    def restyle_asset(request: RestyleRequest):
        """风格迁移（功能）：保持角色与构图，把原画转成目标风格。"""

        from studio.backend.model_service.service import ImageEditProvider

        asset = _resolve_asset(runtime, request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        base = (asset.get("image") or {}).get("url") or (asset.get("source") or {}).get(
            "ai_image", {}
        ).get("url")
        if not base:
            raise HTTPException(status_code=409, detail="该资产没有 AI 原画，无法风格迁移")
        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="自定义模型未启用或缺少 API Key")

        prompts = {
            "pixel": "把这张图转换成像素艺术风格游戏素材：干净的1像素描边、有限的16色调色板、清晰的网格感，保持角色的姿势、服装、配色和所有细节不变，纯色背景",
            "anime": "把这张图转换成2D动漫赛璐璐上色风格：干净的线稿、平整的色块、柔和阴影，保持角色的姿势、服装、配色和所有细节不变，纯色背景",
            "ink": "把这张图转换成中国水墨画风格：写意笔触、墨分五色、留白构图，保持角色的姿势、服装和所有细节可辨识，浅色宣纸底",
        }
        instruction = prompts.get(request.style)
        if not instruction:
            raise HTTPException(status_code=422, detail="style 仅支持 pixel / anime / ink")

        editor = ImageEditProvider(settings)
        try:
            result = editor.edit(base, instruction)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        payload = {
            "style": request.style,
            "url": result.get("url"),
            "file": result.get("file"),
            "model": result.get("model"),
        }
        asset["restyle"] = payload
        saved = dict(asset)
        runtime.assets.save(saved)
        runtime.history.patch_asset(request.asset_id, {"restyle": payload})
        return payload

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

    @router.get("/plan/capabilities")
    def plan_capabilities():
        """能力自省（扩展性）：规划器可调度能力清单。"""

        from studio.backend.plan_service import capabilities

        return capabilities()

    @router.get("/playtest/previews")
    def playtest_previews(asset_id: str | None = None):
        """试玩舞台动作预览。

        有资产时绑定「当前角色的真实源图」：Character Rig 提取 → 分区变形
        （与动画工作台骨骼模式同一条链路），不同角色得到各自的外观与动作；
        没有资产（或源图解析失败）时才回退默认演示角色。条带图统一裁掉
        空白边并返回真实帧尺寸，前端据此按角色实际比例摆放、脚底贴地。
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
        actions = ["idle", "walk", "run", "attack", "jump"]

        # 仅使用显式传入的 asset：没有 asset_id 时一律默认演示角色，
        # 不做 latest 回退（避免历史资产劫持试玩区）
        asset = _resolve_asset(runtime, asset_id) if asset_id else None

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

        PLAYTEST_CACHE_VERSION = 3  # 渲染语义变化（透明底/trim/帧数/尺寸）时 +1，作废旧缓存

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

        engine = "rigged" if source_hash else "procedural"
        seed_key = "rig-{}".format(source_hash) if source_hash else _procedural_seed()

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
                x0 = max(0, x0 - pad)
                y0 = max(0, y0 - pad)
                x1 = min(sheet.width, x1 + pad)
                y1 = min(sheet.height, y1 + pad)
                # 帧宽对齐：裁剪后总宽必须是帧数的整数倍
                x1 = x0 + max(1, (x1 - x0) // len(frames)) * len(frames)
                sheet = sheet.crop((x0, y0, x1, y1))
            return sheet

        pending = [
            action
            for action in actions
            if not os.path.isfile(
                os.path.join(
                    cache_dir, "play_{}_{}.png".format(action, _digest(engine, seed_key, action))
                )
            )
        ]

        # 第二步：真的需要渲染时才做昂贵准备 —— 一次 AI 主体分割（五动作
        # 共享同一 mask），一次骨架提取；复杂背景由分割解决，经典洪泛兜底
        rig = None
        segment_mask = None
        if source is not None and pending:
            if not _source_is_transparent(source):
                settings = runtime.model_settings.effective()
                if settings.get("enabled") and settings.get("api_key"):
                    try:
                        from studio.backend.animation_service.service import (
                            ai_segment_subject,
                        )

                        segment_mask = ai_segment_subject(
                            source, PLAYTEST_SIZE, settings, deadline=time.time() + 45.0
                        )
                    except Exception:
                        segment_mask = None
            try:
                from artgen.rig import build_rig

                rig = build_rig(source, PLAYTEST_SIZE, segment_mask=segment_mask)
            except Exception:
                rig = None

        if source is not None and rig is not None and pending:
            from artgen.riganim import animate_rigged

            def _render(action: str):
                return animate_rigged(
                    source,
                    action,
                    PLAYTEST_FRAMES,
                    PLAYTEST_SIZE,
                    rig=rig,
                    segment_mask=segment_mask,
                    keep_background=False,
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
        # 视频驱动动画时，用其真实帧拼条带（20 帧真实运动）；未生成的动作
        # 回退 rigged/procedural 渲染，前端对缺失动作显示「生成 AI 动画」入口。
        ai_strips: dict[str, dict] = {}
        if asset_id:
            import glob as _glob

            for meta_path in _glob.glob(os.path.join(ANIMATION_DIR, "*.json")):
                try:
                    with open(meta_path, "r", encoding="utf-8") as handle:
                        meta = json.load(handle)
                except (ValueError, OSError):
                    continue
                if meta.get("asset_id") != asset_id:
                    continue
                action_name = meta.get("requested_action")
                frame_urls = meta.get("frame_urls") or []
                if action_name not in actions or len(frame_urls) < 4:
                    continue
                stamp = meta.get("created_at", 0)
                prev = ai_strips.get(action_name)
                if prev is None or stamp > prev.get("created_at", 0):
                    ai_strips[action_name] = meta

        def _pack_ai_strip(meta):
            """把 AI 动画的本地逐帧拼成条带 PNG（与 strips 结构统一，
            前端播放器零改动），缓存于 play_cache。"""

            frame_files = []
            for url in meta.get("frame_urls") or []:
                name = os.path.basename(url)
                path = os.path.join(ANIMATION_DIR, name)
                frame_files.append(path if os.path.isfile(path) else None)

            import hashlib as _hashlib

            digest = _hashlib.sha1(
                ("ai|{}|{}".format(meta.get("id"), len(frame_files))).encode()
            ).hexdigest()[:10]
            out_name = "play_ai_{}_{}.png".format(meta.get("requested_action"), digest)
            out_path = os.path.join(cache_dir, out_name)
            samples = [f for f in frame_files if f]
            samples = [f for f in frame_files if f]
            if len(samples) < 4:
                return None
            if not os.path.isfile(out_path):
                images = [PILImage.open(f).convert("RGBA") for f in samples]
                frame_w = max(img.width for img in images)
                frame_h = max(img.height for img in images)
                sheet = PILImage.new("RGBA", (frame_w * len(images), frame_h), (0, 0, 0, 0))
                for i, img in enumerate(images):
                    sheet.paste(img, (i * frame_w + (frame_w - img.width) // 2, frame_h - img.height))
                sheet.save(out_path, "PNG")
            with PILImage.open(out_path) as handle:
                frame_w, frame_h = handle.size
            return {
                "url": "/api/animation/play_cache/" + out_name,
                "frames": len(samples),
                "width": frame_w,
                "height": frame_h,
                "fps": meta.get("fps", 12),
                "engine": "ai-video",
            }

        previews: dict[str, str] = {}
        strips: dict[str, dict] = {}
        for action in actions:
            ai_meta = ai_strips.get(action)
            if ai_meta is not None:
                packed = _pack_ai_strip(ai_meta)
                if packed:
                    previews[action] = packed["url"]
                    strips[action] = packed
                    continue
            strip_path = os.path.join(
                cache_dir, "play_{}_{}.png".format(action, _digest(engine, seed_key, action))
            )
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
            }

        character = None
        if engine == "rigged" and source_hash:
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
        }

    # ------------------------------------------------------------------
    # P1-B 批量生成与批量导出
    # ------------------------------------------------------------------

    @router.post("/batch", status_code=202)
    def start_batch(request: BatchRequest):
        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="goal is required")
        if request.count not in (4, 9, 12):
            raise HTTPException(status_code=422, detail="count 仅支持 4 / 9 / 12")
        batch_id = runtime.start_batch(
            goal, count=request.count, mode=request.mode, overrides=request.overrides
        )
        return {"batch_id": batch_id, "count": request.count, "mode": request.mode}

    @router.get("/batch/{batch_id}")
    def batch_status(batch_id: str):
        snapshot = runtime.batch_snapshot(batch_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown batch")
        return snapshot

    @router.get("/queue/snapshot")
    def queue_snapshot():
        """队列中心：资产批次 + 动作批次聚合快照。

        两个批次存储都在内存（重启即清空），这里合并为单一视图供前端
        轮询；各取最近 20 条，running 计数驱动前端轮询频率。"""

        asset_batches = []
        batches = getattr(runtime, "batches", {})
        for batch_id in sorted(
            batches, key=lambda bid: (batches.get(bid) or {}).get("created_at", 0), reverse=True
        )[:20]:
            snapshot = runtime.batch_snapshot(batch_id)
            if snapshot:
                snapshot["kind"] = "assets"
                asset_batches.append(snapshot)

        from studio.backend.animation_service.service import (
            _ACTION_BATCHES,
            AnimationService,
        )

        action_batches = []
        for batch_id in sorted(
            _ACTION_BATCHES,
            key=lambda bid: (_ACTION_BATCHES.get(bid) or {}).get("created_at", 0),
            reverse=True,
        )[:20]:
            view = AnimationService(ANIMATION_DIR).action_batch_snapshot(batch_id)
            if view:
                view["kind"] = "actions"
                action_batches.append(view)

        merged = asset_batches + action_batches
        return {
            "running": sum(1 for batch in merged if batch.get("status") == "running"),
            "asset_batches": asset_batches,
            "action_batches": action_batches,
        }

    @router.post("/export/batch")
    def export_batch(request: BatchExportRequest):
        from studio.backend.export_service.service import ExportService

        if not request.asset_ids:
            raise HTTPException(status_code=422, detail="asset_ids 不能为空")
        assets = []
        for asset_id in request.asset_ids:
            asset = _resolve_asset(runtime, asset_id)
            if asset is not None:
                assets.append(dict(asset))
        if not assets:
            raise HTTPException(status_code=404, detail="没有可导出的资产")
        result = ExportService(EXPORTS_DIR).export_batch(assets, request.engine)
        result.pop("path", None)
        return result

    # ------------------------------------------------------------------
    # P2 像素工作台：编辑保存 + 编辑版渲染图
    # ------------------------------------------------------------------

    @router.put("/assets/{asset_id}/pixel")
    def save_pixel_edit(asset_id: str, request: PixelEditRequest):
        """保存像素编辑：更新 CreativeAsset 的 pixel.pixels / 调色板，
        服务端把编辑矩阵渲染为 PNG 落盘（edited_png），资产与历史同步。"""

        import re as _re

        from studio.backend.model_service.service import GENERATED_DIR

        asset = _resolve_asset(runtime, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")

        pixels = request.pixels
        size = len(pixels)
        if size == 0 or size > 128 or any(len(row) != size for row in pixels):
            raise HTTPException(status_code=422, detail="pixels 必须是 1..128 的方形矩阵")
        hex_pattern = _re.compile(r"^#[0-9a-fA-F]{6}$")
        cleaned = []
        for row in pixels:
            out_row = []
            for cell in row:
                if cell is None:
                    out_row.append(None)
                elif isinstance(cell, str) and hex_pattern.match(cell):
                    out_row.append(cell.lower())
                else:
                    raise HTTPException(status_code=422, detail="颜色格式必须是 #RRGGBB 或 null")
            cleaned.append(out_row)

        pixel = asset.setdefault("pixel", {})
        pixel["pixels"] = cleaned
        palette_colors = None
        if request.palette:
            palette_colors = []
            for color in request.palette:
                if (
                    isinstance(color, str)
                    and hex_pattern.match(color)
                    and color.lower() not in palette_colors
                ):
                    palette_colors.append(color.lower())
            palette_block = pixel.setdefault("palette", {})
            palette_block["colors"] = palette_colors
            palette_block["max_colors"] = max(
                palette_block.get("max_colors", 0), len(palette_colors)
            )

        # 编辑矩阵 -> PNG（每格 8px，透明底），供资产页/导出直接消费
        try:
            from io import BytesIO

            from PIL import Image as PILImage

            scale = 8
            image = PILImage.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
            load = image.load()
            for y, row in enumerate(cleaned):
                for x, color in enumerate(row):
                    if not color:
                        continue
                    rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
                    for dy in range(scale):
                        for dx in range(scale):
                            load[x * scale + dx, y * scale + dy] = rgb + (255,)
            buffer = BytesIO()
            image.save(buffer, "PNG")
            name = "{}_edited_{:.0f}.png".format(asset_id, time.time() * 1000)
            with open(os.path.join(GENERATED_DIR, name), "wb") as handle:
                handle.write(buffer.getvalue())
            pixel["edited_png"] = "/api/generated/" + name
            pixel["edited_at"] = time.time()
        except Exception:  # noqa: BLE001 - PNG render is best-effort
            pass

        saved = dict(asset)
        runtime.assets.save(saved)
        runtime.history.patch_asset(asset_id, {"pixel": pixel})
        return {
            "status": "ok",
            "asset_id": saved.get("id"),
            "size": size,
            "edited_png": pixel.get("edited_png"),
            "image_url": "/api/assets/{}/image.png?v={:.0f}".format(saved.get("id"), time.time()),
        }

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
        return {"status": "ok", "service": "creativeforge-studio"}

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
