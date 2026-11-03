"""云能力配置路由（S4）：厂商列表、连接配置、密钥、连通性探测与用量。

与生成面（``cloud_routes``）分离：本组路由只处理配置，不触发任何计费调用；
密钥写入走加密存储，出参一律脱敏。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from adapters.cloud_backends import config as cloud_config
from adapters.cloud_backends import providers as cloud_providers
from studio.backend.cloud_service import catalog
from studio.backend.cloud_service.provider_store import CloudProviderStore, CloudProviderStoreError
from studio.backend.cloud_service.usage import CloudUsageLedger

__all__ = ["build_cloud_settings_router"]


def build_cloud_settings_router(runtime, store: CloudProviderStore | None = None):
    router = APIRouter(prefix="/api/settings/cloud")
    provider_store = store or CloudProviderStore(
        settings_provider=lambda: runtime.model_settings.effective()
    )
    usage = CloudUsageLedger()

    @router.get("/providers")
    def list_providers():
        return {
            "enabled": cloud_config.cloud_enabled(),
            "providers": provider_store.list_providers(),
            "readiness": provider_store.readiness(),
            "config": cloud_config.settings_snapshot(),
        }

    @router.put("/providers/{provider_id}")
    def save_provider(provider_id: str, changes: dict):
        if catalog.provider_spec(provider_id) is None:
            raise HTTPException(status_code=404, detail=f"未登记的云厂商：{provider_id}")
        try:
            return provider_store.save(provider_id, changes)
        except CloudProviderStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post("/providers/{provider_id}/test")
    def test_provider(provider_id: str):
        spec = catalog.provider_spec(provider_id)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"未登记的云厂商：{provider_id}")
        try:
            view = provider_store.public(provider_id)
            api_key, source = provider_store.resolve_key(provider_id)
        except CloudProviderStoreError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        result = cloud_providers.probe(
            provider_id,
            api_key=api_key,
            api_base=view["base_url"],
        )
        result.update({"provider": provider_id, "key_source": source, "has_key": bool(api_key)})
        return result

    @router.put("/providers/{provider_id}/key")
    def set_key(provider_id: str, payload: dict):
        if catalog.provider_spec(provider_id) is None:
            raise HTTPException(status_code=404, detail=f"未登记的云厂商：{provider_id}")
        try:
            return provider_store.set_key(provider_id, str(payload.get("api_key") or ""))
        except CloudProviderStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.get("/usage")
    def get_usage():
        snapshot = usage.snapshot()
        snapshot["enabled"] = cloud_config.cloud_enabled()
        return snapshot

    return router
