"""云生成路由（S4）：3D / 图像 / 视频 / 音频 + 厂商可用性。

与 ``routes.py``（2100+ 行）完全分离，只在 ``app.py`` 挂载，避免污染主路由。
3D 与视频走 202 + task_id 轮询（与 ``/animation/tasks`` 同构），
图像与音频同步返回；产物一律落在缓存根内，由 ``/artifacts`` 沙箱伺服。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from adapters.cloud_backends import config as cloud_config
from adapters.cloud_backends import providers as cloud_providers
from adapters.cloud_backends.contracts import extension_v1 as contract
from adapters.cloud_backends.operators import audio, base as op_base, cg_video, image, object_3d
from studio.backend.cloud_service import catalog
from studio.backend.cloud_service.provider_store import CloudProviderStore, CloudProviderStoreError
from studio.backend.cloud_service.usage import CloudUsageLedger

__all__ = ["build_cloud_router", "CloudTaskStore"]

_CAPABILITY_SLOT = {
    "gen_3d_object_cloud": "mesh",
    "gen_image_cloud": "image",
    "gen_cg_video_cloud": "video",
    "gen_audio_cloud": "audio",
}
_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "glb": "model/gltf-binary",
    "gltf": "model/gltf+json",
}


class CloudTaskStore:
    """进程内云任务快照（与 AnimationService 的轮询语义保持一致）。"""

    def __init__(self, ttl: float = 3600.0):
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._ttl = ttl

    def create(self, **fields) -> dict:
        now = time.time()
        task_id = uuid.uuid4().hex[:12]
        snapshot = {
            "id": task_id,
            "status": "running",
            "stage": "queued",
            "progress": 0.0,
            "created_at": now,
            "updated_at": now,
            **fields,
        }
        with self._lock:
            self._evict(now)
            self._tasks[task_id] = snapshot
        return dict(snapshot)

    def update(self, task_id: str, **changes) -> dict | None:
        with self._lock:
            snapshot = self._tasks.get(task_id)
            if snapshot is None:
                return None
            snapshot.update(changes)
            snapshot["updated_at"] = time.time()
            return dict(snapshot)

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            snapshot = self._tasks.get(task_id)
            return dict(snapshot) if snapshot else None

    def _evict(self, now: float) -> None:
        expired = [tid for tid, snap in self._tasks.items() if now - snap["updated_at"] > self._ttl]
        for tid in expired:
            self._tasks.pop(tid, None)


# ── 工具 ────────────────────────────────────────────────────────────────────


def _resolve_asset(runtime, asset_id: str | None) -> dict | None:
    if not asset_id:
        return None
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


def _provider_chain(capability: str, requested: str = "") -> list[str]:
    """按 catalog 优先级与 fallback 链给出候选后端（主后端在前）。"""

    known = catalog.providers_for(capability)
    if not known:
        return []
    requested = str(requested or "").strip()
    if requested and requested in known:
        chain = [requested]
        fallback = catalog.provider_spec(requested).get("fallback")
        if fallback and fallback in known:
            chain.append(fallback)
        chain.extend(pid for pid in known if pid not in chain)
        return chain
    return known


def _slot_bytes(slot: dict) -> int:
    rel_path = slot.get("local_path")
    if not rel_path:
        return 0
    try:
        return os.path.getsize(contract.resolve_local_path(rel_path))
    except (OSError, contract.CloudExtensionError):
        return 0


# ── 路由 ────────────────────────────────────────────────────────────────────


def build_cloud_router(runtime, store: CloudProviderStore | None = None):
    router = APIRouter(prefix="/api/cloud")
    provider_store = store or CloudProviderStore(
        settings_provider=lambda: runtime.model_settings.effective()
    )
    usage = CloudUsageLedger()
    tasks = CloudTaskStore()
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cloud")

    def _build_model(provider_id: str, capability: str):
        spec = catalog.provider_spec(provider_id) or {}
        try:
            view = provider_store.public(provider_id)
            api_key, _source = provider_store.resolve_key(provider_id)
        except CloudProviderStoreError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return cloud_providers.build_model(
            provider_id,
            capability=capability,
            api_key=api_key,
            api_base=view["base_url"],
            model=view["model"] or spec.get("model", ""),
            workspace_id=view.get("workspace_id", ""),
        )

    def _execute(capability: str, asset: dict, payload: dict, provider_id: str) -> dict:
        slot = _CAPABILITY_SLOT[capability]
        model = _build_model(provider_id, capability)
        try:
            if capability == "gen_3d_object_cloud":
                return object_3d.generate(
                    asset,
                    model,
                    prompt=payload.get("prompt"),
                    image_url=payload.get("image_url"),
                    image=payload.get("image"),
                    seed=payload.get("seed"),
                    decimation_target=payload.get("decimation_target"),
                    texture_size=payload.get("texture_size"),
                )
            if capability == "gen_image_cloud":
                return image.generate(
                    asset,
                    model,
                    prompt=str(payload.get("prompt") or ""),
                    size=payload.get("size"),
                    seed=payload.get("seed"),
                )
            if capability == "gen_cg_video_cloud":
                return cg_video.generate(
                    asset,
                    model,
                    prompt=payload.get("prompt"),
                    image_url=payload.get("image_url"),
                    duration=payload.get("duration"),
                    ratio=payload.get("ratio"),
                    seed=payload.get("seed"),
                )
            return audio.generate(
                asset,
                model,
                kind=str(payload.get("kind") or "dialogue"),
                text=str(payload.get("text") or payload.get("prompt") or ""),
                prompt=str(payload.get("prompt") or ""),
                voice=payload.get("voice"),
            )
        finally:
            model.close()

    def _run_with_fallback(capability: str, asset: dict, payload: dict, requested: str) -> dict:
        """按 fallback 链尝试；全部失败返回最后一个失败槽位（不静默）。"""

        slot = _CAPABILITY_SLOT[capability]
        attempts: list[dict] = []
        result: dict = {}
        for provider_id in _provider_chain(capability, requested):
            result = _execute(capability, asset, payload, provider_id)
            attempts.append(
                {
                    "provider": provider_id,
                    "status": result.get("status"),
                    "error_class": result.get("error_class"),
                }
            )
            usage.record(
                provider_id,
                slot,
                bytes_written=_slot_bytes(result),
                error_class=str(result.get("error_class") or ""),
            )
            if result.get("status") == "succeeded":
                break
        if result.get("status") != "succeeded" and not attempts:
            result = op_base.record_failure(
                asset, slot, "", ValueError(f"没有支持 {capability} 的云后端")
            )
        result["attempts"] = attempts
        return result

    def _persist(asset: dict) -> None:
        if not asset.get("id"):
            return
        try:
            runtime.assets.save(asset)
        except Exception:  # 资产存储失败不影响已产出的云产物
            pass

    def _fail_http(result: dict):
        raise HTTPException(
            status_code=502,
            detail="{}: {}".format(
                result.get("error_class") or "server",
                result.get("error_message") or "云生成失败",
            ),
        )

    # ── 3D ────────────────────────────────────────────────────────────────

    @router.post("/3d", status_code=202)
    def create_3d(request: dict):
        if not cloud_config.cloud_enabled():
            raise HTTPException(status_code=503, detail="云生成能力未启用（CF_CLOUD_BACKENDS=off）")
        if not (request.get("prompt") or request.get("image_url")):
            raise HTTPException(status_code=422, detail="需要 prompt 或 image_url 之一")
        snapshot = tasks.create(capability="gen_3d_object_cloud", slot="mesh", provider="")
        asset = _resolve_asset(runtime, request.get("asset_id"))
        asset = asset if asset is not None else {}

        def worker():
            tasks.update(snapshot["id"], stage="generating", progress=15.0)
            try:
                result = _run_with_fallback(
                    "gen_3d_object_cloud", asset, request, request.get("provider", "")
                )
                _persist(asset)
                if result.get("status") == "succeeded":
                    tasks.update(
                        snapshot["id"],
                        status="succeeded",
                        stage="done",
                        progress=100.0,
                        provider=result.get("provider", ""),
                        result=result,
                    )
                else:
                    tasks.update(
                        snapshot["id"],
                        status="failed",
                        stage="failed",
                        error=result.get("error_message", "云生成失败"),
                        error_class=result.get("error_class", "server"),
                        result=result,
                    )
            except Exception as error:  # 线程内异常必须转成失败快照
                tasks.update(
                    snapshot["id"],
                    status="failed",
                    stage="failed",
                    error=str(error),
                    error_class=getattr(error, "error_class", "server"),
                )

        pool.submit(worker)
        return {"task_id": snapshot["id"], "status": "running", "snapshot": snapshot}

    @router.get("/3d/{task_id}")
    def get_3d(task_id: str):
        snapshot = tasks.get(task_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown cloud task")
        return snapshot

    # ── 图像（同步）───────────────────────────────────────────────────────

    @router.post("/image")
    def create_image(request: dict):
        if not cloud_config.cloud_enabled():
            raise HTTPException(status_code=503, detail="云生成能力未启用")
        prompt = str(request.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="需要非空 prompt")
        asset = _resolve_asset(runtime, request.get("asset_id")) or {}
        result = _run_with_fallback("gen_image_cloud", asset, request, request.get("provider", ""))
        _persist(asset)
        if result.get("status") != "succeeded":
            _fail_http(result)
        return result

    # ── 视频（异步）───────────────────────────────────────────────────────

    @router.post("/video", status_code=202)
    def create_video(request: dict):
        if not cloud_config.cloud_enabled():
            raise HTTPException(status_code=503, detail="云生成能力未启用")
        if not (request.get("prompt") or request.get("image_url")):
            raise HTTPException(status_code=422, detail="需要 prompt 或 image_url 之一")
        snapshot = tasks.create(capability="gen_cg_video_cloud", slot="video", provider="")
        asset = _resolve_asset(runtime, request.get("asset_id")) or {}

        def worker():
            tasks.update(snapshot["id"], stage="generating", progress=15.0)
            try:
                result = _run_with_fallback(
                    "gen_cg_video_cloud", asset, request, request.get("provider", "")
                )
                _persist(asset)
                if result.get("status") == "succeeded":
                    tasks.update(
                        snapshot["id"],
                        status="succeeded",
                        stage="done",
                        progress=100.0,
                        provider=result.get("provider", ""),
                        result=result,
                    )
                else:
                    tasks.update(
                        snapshot["id"],
                        status="failed",
                        stage="failed",
                        error=result.get("error_message", "云生成失败"),
                        error_class=result.get("error_class", "server"),
                        result=result,
                    )
            except Exception as error:
                tasks.update(
                    snapshot["id"],
                    status="failed",
                    stage="failed",
                    error=str(error),
                    error_class=getattr(error, "error_class", "server"),
                )

        pool.submit(worker)
        return {"task_id": snapshot["id"], "status": "running", "snapshot": snapshot}

    @router.get("/video/{task_id}")
    def get_video(task_id: str):
        snapshot = tasks.get(task_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown cloud task")
        return snapshot

    # ── 音频（同步）───────────────────────────────────────────────────────

    @router.post("/audio")
    def create_audio(request: dict):
        if not cloud_config.cloud_enabled():
            raise HTTPException(status_code=503, detail="云生成能力未启用")
        if not (request.get("text") or request.get("prompt")):
            raise HTTPException(status_code=422, detail="需要 text 或 prompt 之一")
        asset = _resolve_asset(runtime, request.get("asset_id")) or {}
        result = _run_with_fallback("gen_audio_cloud", asset, request, request.get("provider", ""))
        _persist(asset)
        if result.get("status") != "succeeded":
            _fail_http(result)
        return result

    # ── 厂商可用性 ────────────────────────────────────────────────────────

    @router.get("/providers")
    def list_cloud_providers():
        views = provider_store.list_providers()
        return {
            "enabled": cloud_config.cloud_enabled(),
            "readiness": provider_store.readiness(),
            "providers": views,
            "config": cloud_config.settings_snapshot(),
        }

    # ── 产物伺服（沙箱）───────────────────────────────────────────────────

    @router.get("/artifacts/{rel_path:path}")
    def serve_artifact(rel_path: str):
        try:
            absolute = contract.resolve_local_path(rel_path)
        except contract.CloudExtensionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if not os.path.isfile(absolute):
            raise HTTPException(status_code=404, detail="not found")
        ext = os.path.splitext(absolute)[1].lstrip(".").lower()
        return FileResponse(absolute, media_type=_MEDIA_TYPES.get(ext, "application/octet-stream"))

    return router
