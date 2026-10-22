"""算子公共骨架：产物落点、成功/失败写回、哈希与溯源。

四个算子只描述「能力输入 → wrapper 调用 → 槽位字段」，落盘、沙箱相对路径、
sha256 与失败留痕统一收敛在这里，保证四个槽位的契约写法完全一致。
"""

from __future__ import annotations

import hashlib
import os
import re
import time

from .. import config
from ..client import cloud_client
from ..contracts import extension_v1 as contract

__all__ = [
    "asset_key",
    "new_output_path",
    "relative_path",
    "record_success",
    "record_failure",
    "run_and_record",
    "resolve_asset",
]


def asset_key(asset) -> str:
    """资产目录名：优先 ``id``，退回 ``name``，非法字符收敛为下划线。"""

    raw = ""
    if isinstance(asset, dict):
        raw = str(asset.get("id") or asset.get("name") or "")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return (cleaned or "unbound")[:48]


def new_output_path(asset, slot: str, ext: str, *, name: str = "") -> str:
    """在缓存根内生成产物落点：``artifacts/<asset_key>/<slot>-<ts>.<ext>``。"""

    directory = os.path.join(config.cache_dir(), "artifacts", asset_key(asset))
    os.makedirs(directory, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or slot)[:40] or slot
    return os.path.join(directory, f"{stem}-{int(time.time() * 1000)}.{ext.lstrip('.')}")


def relative_path(abs_path: str) -> str:
    """绝对产物路径 → 契约要求的缓存根内相对路径（正斜杠）。"""

    rel = os.path.relpath(os.path.abspath(abs_path), os.path.abspath(config.cache_dir()))
    clean = contract.safe_rel_path(rel.replace("\\", "/"))
    if clean is None:
        raise contract.CloudExtensionError(f"产物落在缓存根之外：{abs_path}")
    return clean


def _sha256_of(path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def record_success(asset: dict, slot: str, provider: str, output_path: str, **fields) -> dict:
    """把成功产物写回 ``extensions.cloud_backends.<slot>`` 并返回槽位视图。"""

    if slot not in contract.SLOT_NAMES:
        raise contract.CloudExtensionError(f"未知槽位：{slot!r}")
    payload = {
        "status": "succeeded",
        "provider": provider,
        "local_path": relative_path(output_path),
        **(fields or {}),
    }
    digest = _sha256_of(output_path)
    if digest:
        payload["sha256"] = digest
    try:
        payload["bytes"] = os.path.getsize(output_path)
    except OSError:
        pass

    block = contract.read_extension(asset) or {"version": contract.VERSION}
    block = dict(block)
    block[slot] = payload
    contract.write_extension(asset, block)
    return contract.read_extension(asset).get(slot) or payload


def record_failure(asset: dict, slot: str, provider: str, error: Exception) -> dict:
    """失败留痕（R7）：只写状态与错误分类，不保留半成品产物。"""

    error_class = getattr(error, "error_class", None)
    if error_class not in contract.ERROR_CLASSES:
        error_class = "invalid_request" if isinstance(error, ValueError) else "server"
    slot_payload = contract.error_slot(provider, error_class, str(error))
    block = dict(contract.read_extension(asset) or {"version": contract.VERSION})
    block[slot] = slot_payload
    contract.write_extension(asset, block)
    return contract.read_extension(asset).get(slot) or slot_payload


def _provenance(model, cache_key: str) -> dict:
    info = getattr(model, "last_call_info", {}) or {}
    request_hash = str(info.get("cache_key") or cache_key or "")
    if not request_hash:
        request_hash = cloud_client.request_hash(
            {"provider": getattr(model, "PROVIDER", ""), "model": getattr(model, "model", "")}
        )
    provenance = {
        "request_hash": request_hash,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cache_hit": bool(info.get("cached", False)),
    }
    credits = info.get("credits")
    if isinstance(credits, (int, float)) and credits >= 0:
        provenance["credits_estimate"] = int(credits)
    return provenance


def run_and_record(
    model,
    asset: dict,
    slot: str,
    output_path: str,
    *,
    extra: dict | None = None,
    **infer_kwargs,
) -> dict:
    """调用 wrapper → 落盘 → 写回槽位；失败只留痕，不抛出给编排层。"""

    provider = str(getattr(model, "PROVIDER", ""))
    try:
        model.infer_and_save(output_path, **infer_kwargs)
    except cloud_client.CloudAPIError as error:
        return record_failure(asset, slot, provider, error)
    except ValueError as error:
        return record_failure(asset, slot, provider, error)
    except OSError as error:
        return record_failure(asset, slot, provider, error)

    fields = dict(extra or {})
    info = getattr(model, "last_call_info", {}) or {}
    block = contract.read_extension(asset) or {"version": contract.VERSION}
    block = dict(block)
    block["provenance"] = _provenance(model, str(info.get("cache_key") or ""))
    contract.write_extension(asset, block)
    if slot == "audio" and "kind" not in fields:
        fields["kind"] = str(infer_kwargs.get("kind") or "dialogue")
    return record_success(asset, slot, provider, output_path, **fields)


def resolve_asset(asset, *, required: bool = False) -> dict:
    """算子的资产入参校验：纯云能力也总是写回 CreativeAsset 的扩展块。"""

    if isinstance(asset, dict):
        return asset
    if required:
        raise ValueError("需要 CreativeAsset（dict）")
    return {}
