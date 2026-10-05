"""Persistent, single-process benchmark cache for the local Studio server."""

import copy
import hashlib
import logging
import threading
import time
from pathlib import Path

from studio.backend.persistence import atomic_write_json, read_json_recover

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "studio" / "backend" / "data" / "benchmark-report.json"


def source_version():
    """Invalidate disk reports when benchmark inputs or engine code changes."""
    digest = hashlib.sha256(b"studio-benchmark-cache-v1")
    for folder in (
        "benchmark", "precon", "falign", "gimport", "agent", "agents", "adapters",
        "core", "protocol", "schemas", "packages/creative-core",
    ):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.suffix not in (".py", ".json") or any(
                part in {"results", "__pycache__", "node_modules", "i2v_runs", "mos_kit"}
                for part in path.relative_to(ROOT).parts
            ):
                continue
            if path.is_file():
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def run_benchmark():
    from benchmark.evaluation import EvaluationReport

    return EvaluationReport().run()


class BenchmarkCache:
    """Cache successful reports for 10 minutes, coalescing concurrent requests.

    Cold reads run the real evaluator synchronously (the first visitor must
    get real data). Explicit refreshes never block: the caller immediately
    gets the existing report flagged ``cache.refreshing`` while a background
    thread recomputes; repeated refresh clicks coalesce into one run. Failed
    refreshes never replace the last successful report. Each application
    process owns one instance; this is not a distributed cache.
    """

    def __init__(self, path, *, version, runner=run_benchmark, ttl=600, clock=time.time):
        self.path = str(path)
        self.version = version
        self.runner = runner
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        self._generation = 0
        self._refreshing = False
        saved = read_json_recover(self.path)
        valid = (
            isinstance(saved, dict)
            and saved.get("version") == version
            and isinstance(saved.get("cached_at"), (int, float))
            and isinstance(saved.get("report"), dict)
            and {"generated_at", "dataset", "precon", "falign", "gimport", "agent", "cf_score"}
            <= saved["report"].keys()
        )
        self._entry = saved if valid else None

    @property
    def refreshing(self) -> bool:
        """True while a background refresh is in flight (test/polling hook)."""
        with self._lock:
            return self._refreshing

    def _payload(self, entry, *, refreshing: bool) -> dict:
        """Report copy with cache metadata; the stored entry stays clean."""
        payload = copy.deepcopy(entry["report"])
        payload["cache"] = {"cached_at": entry["cached_at"], "refreshing": refreshing}
        return payload

    def _store(self, entry) -> None:
        try:
            atomic_write_json(self.path, entry)
        except OSError:
            logger.warning(
                "Could not persist benchmark report; keeping memory cache", exc_info=True
            )
        self._entry = entry
        self._generation += 1

    def _spawn_refresh_locked(self) -> None:
        """Start one background recompute; further refresh calls coalesce."""
        if self._refreshing:
            return
        self._refreshing = True
        threading.Thread(
            target=self._refresh_worker, daemon=True, name="cf-benchmark-refresh"
        ).start()

    def _refresh_worker(self) -> None:
        try:
            report = self.runner()
            self._store({"version": self.version, "cached_at": self.clock(), "report": report})
        except Exception:  # noqa: BLE001 - 后台失败只保留旧报告，不影响在线服务
            logger.warning("Benchmark background refresh failed; keeping previous report",
                           exc_info=True)
        finally:
            with self._lock:
                self._refreshing = False

    def get(self, *, refresh=False):
        generation = self._generation
        with self._lock:
            if self._entry:
                age = self.clock() - self._entry["cached_at"]
                if not refresh and (0 <= age < self.ttl or self._generation != generation):
                    return self._payload(self._entry, refreshing=self._refreshing)
                if refresh:
                    # 手动刷新：旧报告立即返回，真实评测转后台（合并重复点击）
                    self._spawn_refresh_locked()
                    return self._payload(self._entry, refreshing=True)
                if self._refreshing:
                    # 过期读撞上后台刷新：给旧报告，避免重复计算
                    return self._payload(self._entry, refreshing=True)
            report = self.runner()
            entry = {"version": self.version, "cached_at": self.clock(), "report": report}
            self._store(entry)
            return self._payload(entry, refreshing=False)
