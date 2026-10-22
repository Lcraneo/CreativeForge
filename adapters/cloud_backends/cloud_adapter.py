"""``CloudAssetAdapter``：把云端产物接入主工程的 ``AssetAdapter`` 契约。

职责边界（对应实施计划 S3）：

- **双向映射**：云产物 → ``extensions.cloud_backends``；导出时剥离 provenance（R8）
- **路径沙箱**：``local_path`` 一律相对缓存根，越界即拒绝（R5）
- **零侵入**：只读写 ``extensions.cloud_backends`` 子树，不触碰 CreativeAsset 既有字段（R1）

本适配器不发起网络请求：生成由 operators 完成，适配器只做契约边界的搬运与校验。
"""

from __future__ import annotations

import os
import shutil

from core.adapter import AssetAdapter

from . import config
from .contracts import extension_v1 as contract
from .operators import base as operator_base

__all__ = ["CloudAssetAdapter", "ADAPTER_NAME", "ADAPTER_VERSION", "HANDLES"]

ADAPTER_NAME = "cloud_backends"
ADAPTER_VERSION = "1.0"
#: 适配器可接管的资产类型标记（``can_handle`` 的取值域）
HANDLES = ("cloud", "cloud_backends", "creative_asset", "3d", "image", "video", "audio", "mesh")


class CloudAssetAdapter(AssetAdapter):
    """云后端产物的导入 / 导出适配器（无状态，可复用单例）。"""

    # ── 契约元信息 ────────────────────────────────────────────────────────

    def name(self) -> str:
        return ADAPTER_NAME

    def version(self) -> str:
        return ADAPTER_VERSION

    def can_handle(self, asset_type: str) -> bool:
        return str(asset_type or "").strip().lower() in HANDLES

    # ── 导入：外部产物 → 资产扩展块 ───────────────────────────────────────

    def import_asset(self, source):
        """把一份外部云端产物登记到资产扩展块。

        ``source`` 支持两种形态：

        - ``{"asset": CreativeAsset, "slot": "mesh", "provider": "tripo",
             "path": "<缓存根内相对路径>"}`` —— 登记已有文件
        - 同上但用 ``"bytes"`` 直接给出二进制 —— 落盘后再登记

        返回写入后的资产；不修改任何既有字段。
        """

        if not isinstance(source, dict):
            raise contract.CloudExtensionError("导入源必须是对象（dict）")
        asset = source.get("asset")
        if not isinstance(asset, dict):
            asset = {}
        slot = str(source.get("slot") or "").strip()
        if slot not in contract.SLOT_NAMES:
            raise contract.CloudExtensionError(f"未知槽位：{slot!r}")
        provider = str(source.get("provider") or "").strip()
        if provider not in contract.PROVIDERS:
            raise contract.CloudExtensionError(f"未登记的云厂商：{provider!r}")

        rel_path = contract.safe_rel_path(source.get("path"))
        if rel_path is None and isinstance(source.get("rel_path"), str):
            rel_path = contract.safe_rel_path(source.get("rel_path"))
        if rel_path is None:
            data = source.get("bytes")
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise contract.CloudExtensionError("需要 path（缓存根内相对路径）或非空 bytes")
            output_path = operator_base.new_output_path(asset, slot, str(source.get("ext") or "bin"))
            with open(output_path, "wb") as handle:
                handle.write(bytes(data))
            rel_path = operator_base.relative_path(output_path)

        absolute = contract.resolve_local_path(rel_path)
        if not os.path.isfile(absolute):
            raise contract.CloudExtensionError(f"产物文件不存在：{rel_path}")

        fields = dict(source.get("fields") or {})
        return operator_base.record_success(asset, slot, provider, absolute, **fields)

    # ── 导出：资产 → 可交付视图 ───────────────────────────────────────────

    def export_asset(self, asset):
        """返回可交付视图：剥离 provenance（R8），并列出产物文件。"""

        block = contract.export_view(asset)
        if block is None:
            return {"namespace": contract.NAMESPACE, "version": contract.VERSION, "slots": {}}

        files: list[dict] = []
        for slot in contract.SLOT_NAMES:
            entry = block.get(slot)
            if not isinstance(entry, dict):
                continue
            rel_path = entry.get("local_path")
            if not rel_path:
                continue
            absolute = contract.resolve_local_path(rel_path)
            files.append(
                {
                    "slot": slot,
                    "provider": entry.get("provider", ""),
                    "local_path": rel_path,
                    "absolute_path": absolute,
                    "exists": os.path.isfile(absolute),
                }
            )
        return {
            "namespace": contract.NAMESPACE,
            "version": block.get("version", contract.VERSION),
            "slots": block,
            "files": files,
        }

    # ── 缓存维护（S5 / R5）────────────────────────────────────────────────

    def cache_stats(self) -> dict:
        """缓存目录体积与文件数（供 S5 复核与用量面板）。"""

        root = config.cache_dir()
        total = 0
        count = 0
        for directory, _, names in os.walk(root):
            for name in names:
                try:
                    total += os.path.getsize(os.path.join(directory, name))
                    count += 1
                except OSError:
                    continue
        return {
            "root": root,
            "files": count,
            "bytes": total,
            "max_bytes": config.cache_max_bytes(),
        }

    def clear_cache(self) -> int:
        """清空缓存目录（保留目录本身），返回删除的条目数。"""

        root = config.cache_dir()
        if not os.path.isdir(root):
            return 0
        removed = 0
        for name in os.listdir(root):
            path = os.path.join(root, name)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed += 1
            except OSError:
                continue
        return removed
