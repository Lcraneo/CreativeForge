"""REST API for the Studio frontend."""

import os

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "exports")


class CreateTaskRequest(BaseModel):
    goal: str
    overrides: dict | None = None


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

        asset = runtime.assets.get(asset_id)
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

        asset = runtime.assets.get(asset_id)
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
        """基于资产的 AI 原画生成侧视/背视图（DashScope imageedit）。"""
        from studio.backend.model_service.service import ImageEditProvider

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

        editor = ImageEditProvider(settings)
        views = {"front": {"url": base, "model": (asset.get("image") or {}).get("model")}}
        try:
            views["side"] = editor.edit(base, "Same character exactly, rotated 90 degrees to show the LEFT SIDE profile view of the same character, keep identical colors, outfit and proportions, full body, transparent background")
            views["back"] = editor.edit(base, "Same character exactly, viewed from BEHIND showing its back, keep identical colors, outfit and proportions, full body, transparent background")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        asset["design_views"] = views
        runtime.assets.save(asset)
        runtime.history.patch_asset(asset_id, {"design_views": views})
        return views

    @router.get("/health")
    def health():
        return {"status": "ok", "service": "creativeforge-studio"}

    return router
