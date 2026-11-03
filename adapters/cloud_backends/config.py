"""云生成后端的运行开关与缓存策略（全部读环境变量，带安全缺省值）。

设计约束（对应实施计划 R1–R10 与验收指标）：
  - ``CF_CLOUD_BACKENDS=off`` 时，主工程行为与融合前完全一致（零侵入）；
  - ``CF_SIDECAR_ENABLED`` 控制 C 部分（本地旁路）接缝，本期固定关闭；
  - 缓存目录 / TTL / 上限可配置，默认上限 500 MB、TTL 7 天；
  - 本模块只做读取，不落盘、不持有任何密钥。

统一以函数形式暴露，便于测试通过 ``os.environ`` 覆盖（不在 import 期冻结）。
"""

from __future__ import annotations

import os

__all__ = [
    "project_root",
    "cloud_enabled",
    "sidecar_enabled",
    "cache_dir",
    "cache_ttl_seconds",
    "cache_max_bytes",
    "request_timeout",
    "max_retries",
    "settings_snapshot",
]

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

_DEFAULT_TTL_DAYS = 7
_DEFAULT_CACHE_MAX_MB = 500
_DEFAULT_TIMEOUT = 60
_DEFAULT_RETRIES = 3


def project_root() -> str:
    """仓库根目录：以本文件为锚点回退三级（adapters/cloud_backends/config.py）。"""

    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def _int_env(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, "")).strip())
    except ValueError:
        return default
    return value if value > 0 else default


def cloud_enabled() -> bool:
    """A 部分总开关；关闭时所有云能力注册与调用一律旁路。"""

    return _flag("CF_CLOUD_BACKENDS", True)


def sidecar_enabled() -> bool:
    """C 部分（本地模型旁路服务）开关；本期固定关闭，仅保留接缝。"""

    return _flag("CF_SIDECAR_ENABLED", False)


def cache_dir() -> str:
    """云产物与响应缓存目录（必须在此目录内，见契约规则 R5）。"""

    configured = os.environ.get("CF_CLOUD_CACHE_DIR", "").strip()
    if configured:
        return os.path.abspath(configured)
    return os.path.join(project_root(), "studio", "backend", "data", "cloud_backends")


def cache_ttl_seconds() -> int:
    return _int_env("CF_CLOUD_CACHE_TTL_DAYS", _DEFAULT_TTL_DAYS) * 24 * 3600


def cache_max_bytes() -> int:
    return _int_env("CF_CLOUD_CACHE_MAX_MB", _DEFAULT_CACHE_MAX_MB) * 1024 * 1024


def request_timeout() -> int:
    return _int_env("CF_CLOUD_TIMEOUT", _DEFAULT_TIMEOUT)


def max_retries() -> int:
    return _int_env("CF_CLOUD_MAX_RETRIES", _DEFAULT_RETRIES)


def settings_snapshot() -> dict:
    """面向前端的非敏感配置视图（不含任何密钥）。"""

    return {
        "enabled": cloud_enabled(),
        "sidecar_enabled": sidecar_enabled(),
        "cache_dir": cache_dir(),
        "cache_ttl_days": cache_ttl_seconds() // (24 * 3600),
        "cache_max_mb": cache_max_bytes() // (1024 * 1024),
        "timeout": request_timeout(),
        "max_retries": max_retries(),
    }
