"""Offline cache regression tests; no model API or running server required."""

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

from studio.backend.benchmark_service import BenchmarkCache
from studio.backend.persistence import atomic_write_json


def report(value=1):
    return dict(generated_at="2026-10-05T00:00:00Z", dataset={"size": value},
                precon={}, falign={}, gimport={}, agent={}, cf_score={})


class BenchmarkCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "benchmark.json"
        self.now = 1000
        self.runner = Mock(return_value=report())

    def cache(self, **kwargs):
        return BenchmarkCache(self.path, version=kwargs.pop("version", "v1"),
                              runner=self.runner, clock=lambda: self.now, **kwargs)

    def served(self, cached_at, refreshing=False):
        """get() 的返回契约：报告本体 + cache 元数据（refreshing 标记）。"""
        return {**report(), "cache": {"cached_at": cached_at, "refreshing": refreshing}}

    def wait_idle(self, cache, timeout=5.0):
        """后台刷新线程跑完（Mock runner 无耗时，轮询即可确定性等待）。"""
        deadline = time.monotonic() + timeout
        while cache.refreshing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(cache.refreshing, "background refresh did not finish in time")

    def test_reuses_memory_and_disk_without_recalculation(self):
        cache = self.cache()
        first = cache.get()
        first["dataset"]["size"] = 99
        self.assertEqual(cache.get(), self.served(self.now))
        self.assertEqual(self.cache().get(), self.served(self.now))
        self.runner.assert_called_once()

    def test_expired_read_runs_real_evaluator_synchronously(self):
        cache = self.cache()
        cache.get()
        self.now += 599
        cache.get()
        self.assertEqual(self.runner.call_count, 1)
        self.now += 1  # 过期：普通读同步重算（浏览到过期报告时拿到真实数据）
        self.assertEqual(cache.get(), self.served(self.now))
        self.assertEqual(self.runner.call_count, 2)

    def test_manual_refresh_returns_stale_immediately_and_recomputes_in_background(self):
        cache = self.cache()
        cache.get()
        self.now += 1
        stale = cache.get(refresh=True)
        self.assertEqual(stale, self.served(cached_at=1000, refreshing=True))
        self.wait_idle(cache)
        self.assertEqual(cache.get(), self.served(self.now))
        self.assertEqual(self.runner.call_count, 2)

    def test_repeated_refresh_clicks_coalesce_into_one_run(self):
        cache = self.cache()
        cache.get()
        entered = threading.Event()
        release = threading.Event()

        def slow():
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test worker was not released")
            return report()

        self.runner.side_effect = slow
        self.assertTrue(cache.get(refresh=True)["cache"]["refreshing"])
        self.assertTrue(entered.wait(timeout=5))  # 后台线程已进入评测
        self.assertTrue(cache.get(refresh=True)["cache"]["refreshing"])  # 重复点击合并
        release.set()
        self.wait_idle(cache)
        self.assertEqual(self.runner.call_count, 2)  # 冷启动 1 次 + 后台 1 次

    def test_failed_background_refresh_preserves_successful_report(self):
        cache = self.cache()
        cache.get()
        self.runner.side_effect = RuntimeError("evaluation failed")
        stale = cache.get(refresh=True)
        self.assertTrue(stale["cache"]["refreshing"])
        self.wait_idle(cache)
        self.assertEqual(cache.get(), self.served(self.now))
        self.assertEqual(self.cache().get(), self.served(self.now))
        self.assertEqual(self.runner.call_count, 2)

    def test_expired_read_during_background_refresh_serves_stale(self):
        cache = self.cache()
        cache.get()
        entered = threading.Event()
        release = threading.Event()

        def slow():
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test worker was not released")
            return report()

        self.runner.side_effect = slow
        cache.get(refresh=True)
        self.assertTrue(entered.wait(timeout=5))
        self.now += cache.ttl + 1
        expired = cache.get()  # 过期读撞上后台刷新：给旧报告，不重复计算
        self.assertEqual(expired["cache"]["refreshing"], True)
        release.set()
        self.wait_idle(cache)
        self.assertEqual(self.runner.call_count, 2)

    def test_code_version_change_invalidates_disk_report(self):
        self.cache().get()
        self.cache(version="v2").get()
        self.assertEqual(self.runner.call_count, 2)

    def test_invalid_cache_is_rebuilt(self):
        for data in ({"version": "v1", "cached_at": "bad", "report": report()},
                     {"version": "v1", "cached_at": self.now, "report": {}}):
            atomic_write_json(str(self.path), data)
            self.assertEqual(self.cache().get(), self.served(self.now))
        self.assertEqual(self.runner.call_count, 2)

    def test_concurrent_cold_reads_share_one_calculation(self):
        entered = threading.Event()
        release = threading.Event()

        def evaluate():
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test worker was not released")
            return report()

        self.runner.side_effect = evaluate
        cache = self.cache()
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(cache.get)
            self.assertTrue(entered.wait(timeout=5))
            others = [pool.submit(cache.get) for _ in range(3)]
            release.set()
            self.assertEqual([future.result(timeout=5) for future in [first, *others]],
                             [self.served(self.now)] * 4)
        self.runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
