"""云厂商凭据与连接配置的加密存储。

与模型广场的 ``ModelSettingsStore`` 并列、互不侵入：

- 模型广场负责 OpenAI 兼容的「一条连接 + 多能力模型名」；
- 本存储负责「每厂商独立端点 + 独立密钥 + 能力声明」。

安全约定（与对象存储配置同一套标准）：

- 密钥只以 Fernet 密文落盘，文件名 ``data/.cloud_secret`` 首次访问生成；
- 出 API 一律脱敏（``mask_secret``），禁止明文回显；
- 环境变量优先于本地存储，便于 CI 与容器部署；
- ``credential_ref`` 支持复用模型广场已保存的凭据（如 ARK 复用 volcengine），
  避免用户为同一把 Key 配置两次。

本模块不发起任何网络请求，连通性探测在 S4 的配置路由中实现。
"""

from __future__ import annotations

import os
import threading
import time

from studio.backend.persistence import atomic_write_json, read_json_recover
from studio.backend.storage_service.interface import mask_secret

from . import catalog

__all__ = ["CloudProviderStore", "CloudProviderStoreError", "DATA_DIR"]

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
PROVIDERS_FILE = os.path.join(DATA_DIR, "cloud_providers.json")
SECRET_FILE = os.path.join(DATA_DIR, ".cloud_secret")

_EDITABLE_FIELDS = ("enabled", "base_url", "model", "workspace_id")


class CloudProviderStoreError(RuntimeError):
    """配置读写失败（未知厂商、类型非法、缺少加密依赖等）。"""


def _fernet(key_file: str):
    """取得 Fernet 实例；密钥文件缺失则生成（权限 0600）。"""

    from cryptography.fernet import Fernet

    os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
    if os.path.isfile(key_file):
        with open(key_file, "rb") as handle:
            key = handle.read().strip()
        if key:
            return Fernet(key)

    key = Fernet.generate_key()
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # 并发首次写入：直接读对方生成的密钥
        with open(key_file, "rb") as handle:
            return Fernet(handle.read().strip())
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass  # Windows 上 chmod 仅部分生效
    return Fernet(key)


class CloudProviderStore:
    """每厂商一条配置记录的加密注册表。"""

    def __init__(self, path=None, secret_file=None, settings_provider=None):
        self.path = path or PROVIDERS_FILE
        self._secret_file = secret_file or SECRET_FILE
        self._settings_provider = settings_provider
        self._lock = threading.Lock()
        self._data: dict = self._load()

    # ── 持久化 ────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        raw = read_json_recover(self.path)
        if not isinstance(raw, dict):
            return {}
        return {
            pid: record
            for pid, record in raw.items()
            if pid in catalog.PROVIDER_CATALOG and isinstance(record, dict)
        }

    def _save(self) -> None:
        try:
            atomic_write_json(self.path, self._data)
        except OSError as error:  # 读写失败不应该把进程带崩
            raise CloudProviderStoreError(f"配置写入失败：{error}") from error

    # ── 凭据解密 / 复用 ───────────────────────────────────────────────────

    def _decrypt(self, token: str) -> str:
        try:
            return _fernet(self._secret_file).decrypt(token.encode()).decode()
        except ImportError as error:
            raise CloudProviderStoreError(
                "缺少 cryptography 依赖，无法解密云厂商密钥（pip install cryptography）"
            ) from error
        except Exception:  # 密文损坏或密钥文件被替换
            return ""

    def _encrypt(self, plain: str) -> str:
        try:
            return _fernet(self._secret_file).encrypt(plain.encode()).decode()
        except ImportError as error:
            raise CloudProviderStoreError(
                "缺少 cryptography 依赖，无法加密云厂商密钥（pip install cryptography）"
            ) from error

    def _from_model_settings(self, ref: str) -> str:
        """解析 ``model_settings:<provider>:<field>`` 形式的凭据复用声明。"""

        parts = ref.split(":")
        if len(parts) != 3 or parts[0] != "model_settings":
            return ""
        field = parts[2]
        try:
            if self._settings_provider is not None:
                effective = self._settings_provider()
            else:
                from studio.backend.model_service.service import ModelSettingsStore

                effective = ModelSettingsStore().effective()
        except Exception:
            return ""
        if not isinstance(effective, dict):
            return ""
        provider = parts[1]
        configured = str(effective.get("provider") or "").strip()
        if provider and configured and provider != configured:
            return ""
        return str(effective.get(field) or "").strip()

    def resolve_key(self, provider_id: str) -> tuple[str, str]:
        """按「环境变量 → 本地密文 → 模型广场复用」顺序取密钥。

        返回 ``(key, source)``，``source`` ∈ ``env`` / ``store`` / ``credential_ref`` / ``""``。
        """

        spec = catalog.provider_spec(provider_id)
        if spec is None:
            raise CloudProviderStoreError(f"未登记的云厂商：{provider_id!r}")

        for env_name in spec.get("env_keys", ()):
            value = os.environ.get(env_name, "").strip()
            if value:
                return value, "env"

        with self._lock:
            record = dict(self._data.get(provider_id) or {})
        token = str(record.get("api_key_enc") or "")
        if token:
            plain = self._decrypt(token)
            if plain:
                return plain, "store"

        ref = spec.get("credential_ref")
        if ref:
            reused = self._from_model_settings(ref)
            if reused:
                return reused, "credential_ref"
        return "", ""

    # ── 读写 ──────────────────────────────────────────────────────────────

    def _merged(self, provider_id: str) -> dict:
        spec = catalog.provider_spec(provider_id)
        if spec is None:
            raise CloudProviderStoreError(f"未登记的云厂商：{provider_id!r}")
        record = dict(self._data.get(provider_id) or {})
        workspace_id = str(record.get("workspace_id") or "").strip()
        base_url = str(record.get("base_url") or spec["base_url"])
        if "{workspace_id}" in base_url:
            base_url = (
                base_url.replace("{workspace_id}", workspace_id) if workspace_id else base_url
            )
        missing = [
            field
            for field in (spec.get("extra_fields") or ())
            if not str(record.get(field) or "").strip()
        ]
        return {
            "id": provider_id,
            "label": spec["label"],
            "capabilities": list(spec["capabilities"]),
            "slot": spec["slot"],
            "protocol": spec["protocol"],
            "env_keys": list(spec["env_keys"]),
            "credential_ref": spec["credential_ref"],
            "notes": spec["notes"],
            "free_tier": spec["free_tier"],
            "price_note": spec.get("price_note", ""),
            "priority": spec["priority"],
            "fallback": spec["fallback"],
            "enabled": bool(record.get("enabled", True)),
            "base_url": base_url,
            "model": str(record.get("model") or spec["model"]),
            "workspace_id": workspace_id,
            "missing_fields": missing,
            "updated_at": float(record.get("updated_at") or 0.0),
        }

    def public(self, provider_id: str) -> dict:
        """单个厂商的脱敏视图（禁止明文回显密钥）。"""

        view = self._merged(provider_id)
        key, source = self.resolve_key(provider_id)
        view.update(
            {
                "has_key": bool(key),
                "key_hint": mask_secret(key),
                "key_source": source,
                "configured": bool(key) and view["enabled"] and not view["missing_fields"],
            }
        )
        return view

    def list_providers(self) -> list[dict]:
        """全部厂商的脱敏视图，按目录声明顺序返回。"""

        return [self.public(pid) for pid in catalog.PROVIDER_IDS]

    def save(self, provider_id: str, changes: dict) -> dict:
        """保存非敏感配置（``enabled`` / ``base_url`` / ``model``）。

        未知字段静默忽略；密钥必须走 ``set_key``，避免明文误落盘。
        """

        if catalog.provider_spec(provider_id) is None:
            raise CloudProviderStoreError(f"未登记的云厂商：{provider_id!r}")
        if not isinstance(changes, dict):
            raise CloudProviderStoreError("配置变更必须是对象（dict）")

        patch: dict = {}
        for field in _EDITABLE_FIELDS:
            if field not in changes:
                continue
            value = changes[field]
            if field == "enabled":
                if not isinstance(value, bool):
                    raise CloudProviderStoreError("enabled 必须是布尔值")
                patch[field] = value
                continue
            if not isinstance(value, str):
                raise CloudProviderStoreError(f"{field} 必须是字符串")
            patch[field] = value.strip()

        with self._lock:
            record = dict(self._data.get(provider_id) or {})
            record.update(patch)
            record["updated_at"] = time.time()
            self._data[provider_id] = record
            self._save()
        return self.public(provider_id)

    def set_key(self, provider_id: str, api_key: str) -> dict:
        """写入密钥（加密落盘）；空串等价于清除。"""

        if catalog.provider_spec(provider_id) is None:
            raise CloudProviderStoreError(f"未登记的云厂商：{provider_id!r}")
        key = str(api_key or "").strip()
        if not key:
            return self.clear_key(provider_id)

        token = self._encrypt(key)
        with self._lock:
            record = dict(self._data.get(provider_id) or {})
            record["api_key_enc"] = token
            record["updated_at"] = time.time()
            self._data[provider_id] = record
            self._save()
        return self.public(provider_id)

    def clear_key(self, provider_id: str) -> dict:
        if catalog.provider_spec(provider_id) is None:
            raise CloudProviderStoreError(f"未登记的云厂商：{provider_id!r}")
        with self._lock:
            record = dict(self._data.get(provider_id) or {})
            record.pop("api_key_enc", None)
            record["updated_at"] = time.time()
            self._data[provider_id] = record
            self._save()
        return self.public(provider_id)

    def readiness(self) -> dict:
        """各能力是否至少有一个可用后端（供生成路由灰化按钮）。"""

        result: dict = {}
        for pid in catalog.PROVIDER_IDS:
            view = self.public(pid)
            for capability in view["capabilities"]:
                result[capability] = result.get(capability, False) or view["configured"]
        return result
