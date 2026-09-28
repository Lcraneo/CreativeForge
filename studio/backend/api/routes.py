"""REST API for the Studio frontend."""

import base64
import os

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "exports")
ANIMATION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "animation")


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


class ModelSettingsRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    chat_model: str | None = None
    use_chat: bool | None = None
    use_image: bool | None = None
    size: str | None = None
    timeout: int | None = None


def build_router(runtime):
    router = APIRouter(prefix="/api")

    @router.post("/tasks", status_code=202)
    def create_task(request: CreateTaskRequest):
        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="goal is required")
        task_id = runtime.start_task(goal, overrides=request.overrides)
        return {
            "task_id": task_id,
            "status": "running",
            "stream_url": "/ws/tasks/{}/stream".format(task_id)
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
            "messages": result.get("messages")
        }

    @router.get("/assets")
    def list_assets():
        return {"assets": runtime.assets.list()}

    @router.get("/assets/latest")
    def latest_asset():
        asset = runtime.assets.latest()
        if asset is None:
            raise HTTPException(status_code=404, detail="no asset yet")
        return asset

    @router.get("/assets/{asset_id}")
    def get_asset(asset_id: str):
        asset = runtime.assets.get(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown asset")
        return asset

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

    @router.get("/exports/{package_name}")
    def download_package(package_name: str):
        path = os.path.join(EXPORTS_DIR, package_name)
        if not os.path.isfile(path) or not package_name.endswith(".zip"):
            raise HTTPException(status_code=404, detail="unknown package")
        return FileResponse(
            path,
            media_type="application/zip",
            filename=package_name
        )

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
        records = runtime.history.list(limit=limit, engine=engine, keyword=q)
        return {"records": records, "total": runtime.history.count()}

    @router.get("/history/{record_id}")
    def get_history(record_id: str):
        record = runtime.history.get(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown history record")
        return record

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

    @router.put("/settings/model")
    def update_model_settings(request: ModelSettingsRequest):
        return runtime.model_settings.update(request.model_dump(exclude_unset=True))

    @router.post("/settings/model/test")
    def test_model_settings():
        from studio.backend.model_service.service import ImageProvider

        return ImageProvider(runtime.model_settings.effective()).test()

    @router.delete("/settings/model/key")
    def clear_model_key():
        return runtime.model_settings.clear_key()

    @router.get("/generated/{name}")
    def generated_image(name: str):
        from studio.backend.model_service.service import safe_generated_path

        path = safe_generated_path(name)
        if path is None:
            raise HTTPException(status_code=404, detail="unknown image")
        return FileResponse(path)

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
        base = (asset.get("image") or {}).get("url") or (asset.get("source") or {}).get("ai_image", {}).get("url")
        if not base:
            raise HTTPException(status_code=409, detail="该资产没有 AI 原画，无法生成三视图（先在工作台用自定义模型生成）")

        settings = runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            raise HTTPException(status_code=409, detail="自定义模型未启用或缺少 API Key")

        from studio.backend.model_service.service import generate_turnaround

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
                raise HTTPException(status_code=409, detail="AI 视频驱动需要先在模型设置中启用自定义模型")
            try:
                return service.create_video(
                    source_bytes=source,
                    settings=settings,
                    action=request.action,
                    fps=request.fps,
                    duration=request.duration,
                    size=request.size,
                )
            except RuntimeError as error:
                raise HTTPException(status_code=502, detail=str(error))
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

    @router.post("/animation/preview-frame")
    def preview_animation_frame(request: PreviewFrameRequest):
        """渲染动作循环内的单帧 PNG（动作编辑器的时间轴/滑杆实时预览）。"""
        from artgen import asset_params
        from artgen.png import encode_rgba
        from artgen.anim import render_frame_rgba
        from artgen.sidewalk import render_side_frame_rgba

        params = {"palette": None, "seed": "preview"}
        if request.asset_id:
            asset = _resolve_asset(runtime, request.asset_id)
            if asset is not None:
                params = asset_params(asset)
        view = request.view if request.view in ("front", "side") else "front"
        phase = max(0.0, min(1.0, float(request.phase)))
        action = request.action if request.action in ("idle", "walk", "run", "attack", "jump") else "walk"
        if view == "side" and action in ("walk", "run"):
            w, h, rgba = render_side_frame_rgba(params, action, phase, request.size, request.pose_config)
        else:
            w, h, rgba = render_frame_rgba(params, action, phase, request.size, request.pose_config)
        return Response(content=encode_rgba(w, h, rgba), media_type="image/png")

    @router.get("/animation/custom-actions")
    def list_custom_actions():
        from studio.backend.animation_service.custom_actions import CustomActionStore

        return {"actions": CustomActionStore(ANIMATION_DIR + "/custom_actions.json").list()}

    @router.post("/animation/custom-actions")
    def save_custom_action(request: CustomActionRequest):
        from studio.backend.animation_service.custom_actions import CustomActionStore

        try:
            saved = CustomActionStore(ANIMATION_DIR + "/custom_actions.json").save(request.model_dump())
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

    @router.get("/animation/{name}")
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

    @router.get("/health")
    def health():
        return {"status": "ok", "service": "creativeforge-studio"}

    return router
