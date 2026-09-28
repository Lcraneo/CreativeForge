"""对象存储配置的加密存储（Fernet + 本机密钥文件）。

安全要求（需求硬约束）：
  - SecretId / SecretKey 等凭证**仅**来自加密配置文件或环境变量，严禁硬编码；
  - 密文落盘：配置文件里的敏感字段是 Fernet token，不是明文；
  - 出 API 一律脱敏（mask_secret），禁止明文回显；
  - 异常与日志文本经过 redact，禁止明文写入日志。

密钥文件 ``data/.storage_secret`` 首次访问自动生成（权限 0600，Windows 上
尽力收紧）。密钥文件丢失时旧密文不可解，按"配置损坏"处理并提示重新录入。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

from .interface import (
    StorageConfig,
    StorageConfigError,
    mask_secret,
)

__all__ = ["StorageConfigStore", "DATA_DIR"]

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
KEY_FILE = os.path.join(DATA_DIR, ".storage_secret")
CONFIGS_FILE = os.path.join(DATA_DIR, "storage_configs.json")

# 环境变量兜底（参考 Windup 的 QINIU_* 约定 + 通用 STORAGE_* 前缀）
_ENV_FILE_CANDIDATES = (
    os.path.join(BACKEND_DIR, ".env"),
    os.path.join(os.path.dirname(BACKEND_DIR), ".env"),
)


def _load_env_file(path: str) -> dict:
    """极简 .env 解析（KEY=VALUE，支持引号与 # 注释），不引第三方依赖。"""
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return values


def _fernet():
    """取得 Fernet 实例；密钥文件不存在则生成（一次性）。"""
    from cryptography.fernet import Fernet

    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.isfile(KEY_FILE):
        with open(KEY_FILE, "rb") as handle:
            key = handle.read().strip()
        if key:
            return Fernet(key)
    key = Fernet.generate_key()
    # O_CREAT|O_EXCL：不覆盖已有密钥（并发安全）
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass  # Windows 上 chmod 仅部分生效
    return Fernet(key)


_SENSITIVE_FIELDS = ("access_key", "secret_key")


class StorageConfigStore:
    """多份云存储配置的加密注册表（新增 / 编辑 / 删除 / 设默认）。"""

    ENV_CONFIG_ID = "__env__"

    def __init__(self, path: str | None = None, key_file: str | None = None):
        self.path = path or CONFIGS_FILE
        self._key_file = key_file or KEY_FILE
        self._lock = threading.Lock()

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not os.path.isfile(self.path):
            return {"version": 1, "configs": []}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and isinstance(data.get("configs"), list):
                return data
        except (ValueError, OSError):
            pass
        return {"version": 1, "configs": []}

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _decrypt_row(self, row: dict) -> StorageConfig:
        fer = _fernet()
        from cryptography.fernet import InvalidToken

        plain: dict = {k: v for k, v in row.items() if k not in _SENSITIVE_FIELDS}
        try:
            for field in _SENSITIVE_FIELDS:
                token = row.get(field, "")
                plain[field] = fer.decrypt(token.encode()).decode() if token else ""
        except InvalidToken as exc:
            raise StorageConfigError(
                "配置密文无法解密（密钥文件已更换或文件损坏），请重新录入凭证"
            ) from exc
        return StorageConfig(**plain)

    @staticmethod
    def _encrypt_config(config: StorageConfig) -> dict:
        fer = _fernet()
        row = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "region": config.region,
            "bucket": config.bucket,
            "endpoint": config.endpoint,
            "is_default": config.is_default,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }
        for field in _SENSITIVE_FIELDS:
            value = getattr(config, field)
            row[field] = fer.encrypt(value.encode()).decode() if value else ""
        return row

    # ── 环境变量兜底 ────────────────────────────────────────────────────────

    def env_config(self) -> StorageConfig | None:
        """从环境变量 / .env 构造内置配置（QINIU_* 或通用 STORAGE_*）。"""
        env = dict(os.environ)
        for candidate in _ENV_FILE_CANDIDATES:
            env.update({k: v for k, v in _load_env_file(candidate).items() if k not in env})
        if env.get("STORAGE_ACCESS_KEY") and env.get("STORAGE_SECRET_KEY"):
            provider = env.get("STORAGE_PROVIDER", "kodo").lower()
            return StorageConfig(
                id=self.ENV_CONFIG_ID,
                name="环境变量默认（%s）" % provider.upper(),
                provider=provider,
                access_key=env["STORAGE_ACCESS_KEY"],
                secret_key=env["STORAGE_SECRET_KEY"],
                region=env.get("STORAGE_REGION", ""),
                bucket=env.get("STORAGE_BUCKET", ""),
                endpoint=env.get("STORAGE_ENDPOINT", ""),
                is_default=False,
            )
        if env.get("QINIU_ACCESS_KEY") and env.get("QINIU_SECRET_KEY"):
            return StorageConfig(
                id=self.ENV_CONFIG_ID,
                name="环境变量默认（七牛 Kodo）",
                provider="kodo",
                access_key=env["QINIU_ACCESS_KEY"],
                secret_key=env["QINIU_SECRET_KEY"],
                region=env.get("QINIU_REGION", env.get("QINIU_REGION_CODE", "cn-east-1")),
                bucket=env.get("QINIU_BUCKET_NAME", env.get("QINIU_BUCKET", "")),
                endpoint=env.get("QINIU_ENDPOINT", ""),
                is_default=False,
            )
        return None

    # ── 对外 API ────────────────────────────────────────────────────────────

    def list_public(self) -> list[dict]:
        """全部配置的脱敏视图（含环境变量兜底项）。"""
        with self._lock:
            rows = self._load()["configs"]
        configs = [self._decrypt_row(row) for row in rows]
        # 环境变量项：仅当没有任何已保存的默认配置时顶上
        env = self.env_config()
        if env and not any(c.is_default for c in configs):
            env.is_default = True
            configs.append(env)
        return [config.public() for config in configs]

    def get(self, config_id: str) -> StorageConfig:
        """按 id 取解密配置（仅后端内部使用，严禁直接出 API）。"""
        if config_id == self.ENV_CONFIG_ID:
            env = self.env_config()
            if env:
                return env
            raise StorageConfigError("环境变量配置不存在（检查 .env 中的凭证）")
        with self._lock:
            rows = self._load()["configs"]
        row = next((r for r in rows if r.get("id") == config_id), None)
        if row is None:
            raise StorageConfigError(f"配置不存在：{config_id}")
        return self._decrypt_row(row)

    def get_default(self) -> StorageConfig | None:
        """默认配置：已保存的默认项 > 环境变量兜底。"""
        with self._lock:
            rows = self._load()["configs"]
        configs = [self._decrypt_row(row) for row in rows]
        default = next((c for c in configs if c.is_default), None)
        if default:
            return default
        env = self.env_config()
        if env:
            env.is_default = True
            return env
        return configs[0] if configs else None

    def create(self, fields: dict) -> dict:
        now = time.time()
        config = StorageConfig(
            id=uuid.uuid4().hex[:12],
            name=str(fields.get("name") or "").strip(),
            provider=str(fields.get("provider") or "").strip().lower(),
            access_key=str(fields.get("access_key") or ""),
            secret_key=str(fields.get("secret_key") or ""),
            region=str(fields.get("region") or "").strip(),
            bucket=str(fields.get("bucket") or "").strip(),
            endpoint=str(fields.get("endpoint") or "").strip(),
            created_at=now,
            updated_at=now,
        )
        self._validate(config)
        with self._lock:
            data = self._load()
            configs = [self._decrypt_row(r) for r in data["configs"]]
            if fields.get("is_default"):
                for c in configs:
                    c.is_default = False
                config.is_default = True
            elif not configs:
                config.is_default = True  # 首条配置自动成为默认
            configs.append(config)
            data["configs"] = [self._encrypt_config(c) for c in configs]
            self._save(data)
        return config.public()

    def update(self, config_id: str, fields: dict) -> dict:
        """编辑配置。敏感字段传 None / 空串表示"保持原值不回显不覆盖"。"""
        with self._lock:
            data = self._load()
            configs = [self._decrypt_row(r) for r in data["configs"]]
            config = next((c for c in configs if c.id == config_id), None)
            if config is None:
                raise StorageConfigError(f"配置不存在：{config_id}")
            for field in ("name", "provider", "region", "bucket", "endpoint"):
                if fields.get(field) is not None:
                    setattr(config, field, str(fields[field]).strip())
            for field in _SENSITIVE_FIELDS:
                value = fields.get(field)
                if value:  # 空串/None = 保持原值（前端不回显明文）
                    setattr(config, field, str(value))
            if fields.get("is_default") is not None and bool(fields["is_default"]):
                for c in configs:
                    c.is_default = c.id == config_id
            config.updated_at = time.time()
            self._validate(config)
            data["configs"] = [self._encrypt_config(c) for c in configs]
            self._save(data)
        return config.public()

    def delete(self, config_id: str) -> dict:
        if config_id == self.ENV_CONFIG_ID:
            raise StorageConfigError("环境变量配置由 .env 管理，不能在界面删除")
        with self._lock:
            data = self._load()
            configs = [self._decrypt_row(r) for r in data["configs"]]
            remaining = [c for c in configs if c.id != config_id]
            if len(remaining) == len(configs):
                raise StorageConfigError(f"配置不存在：{config_id}")
            if remaining and not any(c.is_default for c in remaining):
                remaining[0].is_default = True
            data["configs"] = [self._encrypt_config(c) for c in remaining]
            self._save(data)
        return {"status": "ok", "removed": config_id}

    def set_default(self, config_id: str) -> dict:
        if config_id == self.ENV_CONFIG_ID:
            raise StorageConfigError("环境变量配置始终作为兜底默认，无需设置")
        with self._lock:
            data = self._load()
            configs = [self._decrypt_row(r) for r in data["configs"]]
            target = next((c for c in configs if c.id == config_id), None)
            if target is None:
                raise StorageConfigError(f"配置不存在：{config_id}")
            for c in configs:
                c.is_default = c.id == config_id
            data["configs"] = [self._encrypt_config(c) for c in configs]
            self._save(data)
        return target.public()

    @staticmethod
    def _validate(config: StorageConfig) -> None:
        from .providers import PROVIDER_PRESETS

        if not config.name:
            raise StorageConfigError("配置名称不能为空")
        if config.provider not in PROVIDER_PRESETS:
            raise StorageConfigError(
                f"未知厂商 {config.provider!r}；支持 {sorted(PROVIDER_PRESETS)}"
            )
        if not config.bucket:
            raise StorageConfigError("Bucket 不能为空")
        if not config.access_key or not config.secret_key:
            raise StorageConfigError("缺少访问凭证（SecretId / SecretKey）")
        if not config.endpoint and not config.region:
            raise StorageConfigError("地域与自定义 Endpoint 至少填一项")
