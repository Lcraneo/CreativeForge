"""Offline cache regression tests; no model API or running server required."""

import tempfile
import threading
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

    def test_reuses_memory_and_disk_without_recalculation(self):
        cache = self.cache()
        first = cache.get()
        first["dataset"]["size"] = 99
        self.assertEqual(cache.get(), report())
        self.assertEqual(self.cache().get(), report())
        self.runner.assert_called_once()

    def test_expiry_and_manual_refresh_run_real_evaluator(self):
        cache = self.cache()
        cache.get()
        self.now += 599
        cache.get()
        self.assertEqual(self.runner.call_count, 1)
        self.now += 1
        cache.get()
        cache.get(refresh=True)
        self.assertEqual(self.runner.call_count, 3)

    def test_code_version_change_invalidates_disk_report(self):
        self.cache().get()
        self.cache(version="v2").get()
        self.assertEqual(self.runner.call_count, 2)

    def test_failed_refresh_preserves_successful_report(self):
        cache = self.cache()
        cache.get()
        self.runner.side_effect = RuntimeError("evaluation failed")
        with self.assertRaises(RuntimeError):
            cache.get(refresh=True)
        self.assertEqual(cache.get(), report())
        self.assertEqual(self.cache().get(), report())

    def test_invalid_cache_is_rebuilt(self):
        for data in ({"version": "v1", "cached_at": "bad", "report": report()},
                     {"version": "v1", "cached_at": self.now, "report": {}}):
            atomic_write_json(str(self.path), data)
            self.assertEqual(self.cache().get(), report())
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
                             [report()] * 4)
        self.runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
