"""云生成用量台账：本地计数，供「云能力」面板显示调用次数与缓存命中率。

只做进程内 + JSON 落盘的轻量统计，不请求厂商额度接口（多数厂商不对个人
Key 开放余额查询）。缓存命中单独计数，用于验证 R9「同请求不重复计费」。
"""

from __future__ import annotations

import os
import threading
import time

from studio.backend.persistence import atomic_write_json, read_json_recover

from . import catalog

__all__ = ["CloudUsageLedger", "USAGE_FILE"]

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_FILE = os.path.join(BACKEND_DIR, "data", "cloud_usage.json")


class CloudUsageLedger:
    """按厂商 × 槽位累计调用次数、字节数与缓存命中数。"""

    def __init__(self, path: str | None = None):
        self.path = path or USAGE_FILE
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        raw = read_json_recover(self.path)
        if not isinstance(raw, dict):
            return {}
        return {pid: record for pid, record in raw.items() if isinstance(record, dict)}

    def _save(self) -> None:
        try:
            atomic_write_json(self.path, self._data)
        except OSError:
            pass  # 统计失败不影响主链路

    def record(
        self,
        provider: str,
        slot: str,
        *,
        cached: bool = False,
        bytes_written: int = 0,
        error_class: str = "",
    ) -> None:
        """记录一次调用；``cached=True`` 表示命中缓存（未发生计费）。"""

        pid = str(provider or "unknown")
        key = str(slot or "unknown")
        with self._lock:
            record = dict(self._data.get(pid) or {})
            slots = dict(record.get("slots") or {})
            entry = dict(slots.get(key) or {})
            entry["calls"] = int(entry.get("calls") or 0) + 1
            entry["bytes"] = int(entry.get("bytes") or 0) + max(0, int(bytes_written or 0))
            if cached:
                entry["cache_hits"] = int(entry.get("cache_hits") or 0) + 1
            if error_class:
                errors = dict(entry.get("errors") or {})
                errors[error_class] = int(errors.get(error_class) or 0) + 1
                entry["errors"] = errors
            entry["last_at"] = time.time()
            slots[key] = entry
            record["slots"] = slots
            self._data[pid] = record
            self._save()

    def snapshot(self) -> dict:
        """面向前端的用量视图（附缓存目录体积）。"""

        from adapters.cloud_backends import config as cloud_config

        providers = {}
        totals = {"calls": 0, "cache_hits": 0, "bytes": 0, "errors": 0}
        with self._lock:
            data = {pid: dict(record) for pid, record in self._data.items()}

        for pid in catalog.PROVIDER_IDS:
            record = data.get(pid) or {}
            slots = record.get("slots") or {}
            provider_totals = {"calls": 0, "cache_hits": 0, "bytes": 0, "errors": 0}
            for entry in slots.values():
                if not isinstance(entry, dict):
                    continue
                provider_totals["calls"] += int(entry.get("calls") or 0)
                provider_totals["cache_hits"] += int(entry.get("cache_hits") or 0)
                provider_totals["bytes"] += int(entry.get("bytes") or 0)
                provider_totals["errors"] += sum(int(v) for v in (entry.get("errors") or {}).values())
            providers[pid] = {"slots": slots, **provider_totals}
            for name in totals:
                totals[name] += provider_totals[name]

        root = cloud_config.cache_dir()
        cache_bytes = 0
        cache_files = 0
        for directory, _, names in os.walk(root):
            for name in names:
                try:
                    cache_bytes += os.path.getsize(os.path.join(directory, name))
                    cache_files += 1
                except OSError:
                    continue

        return {
            "providers": providers,
            "totals": totals,
            "cache": {
                "dir": root,
                "files": cache_files,
                "bytes": cache_bytes,
                "max_bytes": cloud_config.cache_max_bytes(),
                "ttl_days": cloud_config.cache_ttl_seconds() // 86400,
            },
        }
