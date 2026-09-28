"""统一对象存储接口（参考 Windup 的 Protocol 端口模式重写）。

Windup 参考项目里有两套存储代码（七牛 SDK + 手写 COS TC3 签名），但它们
形状不同、没有统一抽象，也没有分片/断点续传。本模块把"屏蔽厂商差异"作为
第一目标：调用方只认 :class:`StorageProvider` 这一个端口。

错误形态分级（继承 Windup 的教训：把"鉴权错 / 超时 / 不存在 / 传输失败"
压成一个症状会让排查方向全错）：
  - :class:`StorageAuthError`    凭证或权限问题 → 修配置
  - :class:`StorageTimeoutError` 网络或超时预算耗尽 → 可重试
  - :class:`StorageNotFoundError` 对象/桶不存在 → 修 key
  - :class:`StorageConfigError`  配置缺失或不合法 → 修表单
  - :class:`StorageTransferError` 传输中断（分片失败等）→ 可续传
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "StoredObject",
    "StorageConfig",
    "StorageProvider",
    "StorageError",
    "StorageAuthError",
    "StorageTimeoutError",
    "StorageNotFoundError",
    "StorageConfigError",
    "StorageTransferError",
    "mask_secret",
    "redact",
]

# ── 异常体系 ────────────────────────────────────────────────────────────────


class StorageError(RuntimeError):
    """对象存储统一错误基类。message 必须已经过 redact（不含密钥）。"""


class StorageAuthError(StorageError):
    pass


class StorageTimeoutError(StorageError):
    pass


class StorageNotFoundError(StorageError):
    pass


class StorageConfigError(StorageError):
    pass


class StorageTransferError(StorageError):
    pass


_SECRET_MARKERS = ("secret", "token", "password", "key=")


def redact(text: str) -> str:
    """把字符串里形如 key=xxx 的片段打码。异常进日志前必须过这一道。"""

    import re

    def _mask(match: "re.Match[str]") -> str:
        name, value = match.group(1), match.group(2)
        return f"{name}={mask_secret(value)}"

    return re.sub(r"(?i)\b(\w*(?:secret|token|password|key)\w*)=([^\s,;'\"]+)", _mask, text or "")


def mask_secret(secret: str) -> str:
    """凭证脱敏：保留前 4 后 4，中间打星。空串原样返回。"""

    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}****{secret[-4:]}"


# ── 值对象 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    last_modified: str  # ISO-8601
    etag: str


@dataclass
class StorageConfig:
    """一份对象存储连接配置（对应动画工作台 API 配置表单的一条记录）。

    ``access_key`` / ``secret_key`` 是敏感字段：
      - 存盘前必须加密（见 settings.StorageConfigStore）；
      - 出 API（前端展示）必须 mask_secret；
      - 绝不写日志、绝不进异常文本。
    """

    id: str
    name: str
    provider: str  # oss / cos / kodo / obs / tos / bos
    access_key: str = ""
    secret_key: str = ""  # 敏感：仅加密存储
    region: str = ""
    bucket: str = ""
    endpoint: str = ""  # 自定义 Endpoint（可选，优先于厂商模板）
    is_default: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def public(self) -> dict:
        """面向前端的脱敏视图（禁止明文回显凭证）。"""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "access_key": mask_secret(self.access_key),
            "secret_key": mask_secret(self.secret_key),
            "has_secret": bool(self.access_key and self.secret_key),
            "region": self.region,
            "bucket": self.bucket,
            "endpoint": self.endpoint,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── 统一端口 ────────────────────────────────────────────────────────────────


@runtime_checkable
class StorageProvider(Protocol):
    """屏蔽云厂商差异的统一对象存储端口。

    上传 / 下载 / 列举 / 删除 / 生成临时访问链接。所有实现：
      - 凭证来自 :class:`StorageConfig`（源头是加密配置文件或环境变量）；
      - 网络调用自带超时控制；
      - 抛出的异常归入上面的分级体系，文本经过 redact。
    """

    def upload(self, data: bytes, key: str, *, content_type: str = "application/octet-stream") -> StoredObject: ...

    def download(self, key: str) -> bytes: ...

    def list(self, prefix: str = "", limit: int = 100) -> list[StoredObject]: ...

    def delete(self, key: str) -> None: ...

    def presign(self, key: str, expires: int = 3600) -> str: ...

    def test(self) -> dict:
        """连通性测试：轻量列举（max_keys=1）验证凭证 + 桶可达。"""
        ...
