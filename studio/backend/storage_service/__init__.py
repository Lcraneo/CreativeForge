"""对象存储模块（三渲二改造 · 第二项）。

统一接口（上传 / 下载 / 列举 / 删除 / 临时访问链接）屏蔽六家云厂商差异：
阿里云 OSS / 腾讯云 COS / 七牛云 Kodo / 华为云 OBS / 火山引擎 TOS / 百度智能云 BOS。
S3 兼容协议 + boto3 统一驱动；大文件分片上传、断点续传、失败重试、超时控制；
凭证仅读取加密配置 / 环境变量，严禁硬编码。
"""

from .interface import (
    StorageAuthError,
    StorageConfig,
    StorageConfigError,
    StorageError,
    StorageNotFoundError,
    StorageProvider,
    StorageTimeoutError,
    StorageTransferError,
    StoredObject,
    mask_secret,
    redact,
)
from .providers import PROVIDER_PRESETS, S3CompatProvider, create_provider, resolve_endpoint
from .service import StorageManager, get_storage_manager
from .settings import StorageConfigStore
from .transfer import MultipartManager

__all__ = [
    "StorageAuthError",
    "StorageConfig",
    "StorageConfigError",
    "StorageError",
    "StorageNotFoundError",
    "StorageProvider",
    "StorageTimeoutError",
    "StorageTransferError",
    "StoredObject",
    "mask_secret",
    "redact",
    "PROVIDER_PRESETS",
    "S3CompatProvider",
    "create_provider",
    "resolve_endpoint",
    "StorageConfigStore",
    "MultipartManager",
    "StorageManager",
    "get_storage_manager",
]
