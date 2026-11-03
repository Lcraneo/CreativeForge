"""StorageManager：对象存储模块的门面。

组合三件事：
  - :class:`StorageConfigStore` 加密配置注册表（含环境变量兜底）；
  - :class:`S3CompatProvider` 六厂商统一驱动；
  - :class:`MultipartManager` 分片 / 断点续传会话。

所有对外错误文本经过 redact；凭证只进客户端构造，不进任何日志路径。
"""

from __future__ import annotations

import threading

from .interface import StorageConfig, StorageConfigError, StorageError, redact
from .providers import S3CompatProvider, create_provider
from .settings import StorageConfigStore
from .transfer import MultipartManager

__all__ = ["StorageManager", "get_storage_manager"]

_MANAGER: StorageManager | None = None
_MANAGER_LOCK = threading.Lock()


class StorageManager:
    def __init__(self, store: StorageConfigStore | None = None):
        self.store = store or StorageConfigStore()
        self.multipart = MultipartManager(self._provider_for_config_id)

    # ── provider 解析 ───────────────────────────────────────────────────────

    def _provider_for_config_id(self, config_id: str) -> S3CompatProvider:
        config = self.store.get(config_id)
        return create_provider(config)

    def provider_for(self, config_id: str | None = None) -> S3CompatProvider:
        """config_id 缺省用默认配置；都没有则报配置错误（不静默）。"""
        if config_id:
            return self._provider_for_config_id(config_id)
        default = self.store.get_default()
        if default is None:
            raise StorageConfigError(
                "尚未配置对象存储：在动画工作台「云存储」页新增 API 配置，"
                "或在 .env 写入 QINIU_* / STORAGE_* 环境变量"
            )
        return create_provider(default)

    def default_config_id(self) -> str | None:
        default = self.store.get_default()
        return default.id if default else None

    # ── 统一操作（透传 + 错误规整） ─────────────────────────────────────────

    def upload(
        self,
        data: bytes,
        key: str,
        *,
        config_id: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> dict:
        try:
            obj = self.provider_for(config_id).upload(data, key, content_type=content_type)
            return {"key": obj.key, "size": obj.size}
        except StorageError as exc:
            raise StorageError(redact(str(exc))) from exc

    def download(self, key: str, *, config_id: str | None = None) -> bytes:
        return self.provider_for(config_id).download(key)

    def list(
        self, prefix: str = "", *, config_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        objects = self.provider_for(config_id).list(prefix, limit=limit)
        return [
            {"key": o.key, "size": o.size, "last_modified": o.last_modified, "etag": o.etag}
            for o in objects
        ]

    def delete(self, key: str, *, config_id: str | None = None) -> dict:
        self.provider_for(config_id).delete(key)
        return {"status": "ok", "key": key}

    def presign(self, key: str, *, config_id: str | None = None, expires: int = 3600) -> dict:
        url = self.provider_for(config_id).presign(key, expires=expires)
        return {"key": key, "url": url, "expires": expires}

    # ── 连通性测试 ──────────────────────────────────────────────────────────

    def test_config(self, config_id: str | None = None, payload: dict | None = None) -> dict:
        """测试已保存配置（传 id）或未保存的表单（传 payload）。

        payload 里凭证字段缺省时回落已保存配置（编辑场景只改了地域等非敏感字段）。
        """
        try:
            if payload:
                merged = dict(payload)
                if config_id and not (merged.get("access_key") and merged.get("secret_key")):
                    saved = self.store.get(config_id)
                    merged.setdefault("access_key", saved.access_key)
                    merged.setdefault("secret_key", saved.secret_key)
                config = StorageConfig(
                    id=config_id or "__form__",
                    name=merged.get("name") or "__form__",
                    provider=str(merged.get("provider") or "").lower(),
                    access_key=str(merged.get("access_key") or ""),
                    secret_key=str(merged.get("secret_key") or ""),
                    region=str(merged.get("region") or ""),
                    bucket=str(merged.get("bucket") or ""),
                    endpoint=str(merged.get("endpoint") or ""),
                )
                provider = create_provider(config)
            else:
                provider = self.provider_for(config_id)
            return provider.test()
        except StorageError as exc:
            return {"ok": False, "detail": redact(str(exc))}
        except Exception as exc:  # noqa: BLE001 - 依赖缺失等环境问题
            return {"ok": False, "detail": redact(str(exc))}


def get_storage_manager() -> StorageManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = StorageManager()
        return _MANAGER
