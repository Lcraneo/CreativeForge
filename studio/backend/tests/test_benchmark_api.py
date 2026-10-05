"""Exercise the real FastAPI route with an offline evaluator and temporary cache."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.routes import build_router
from studio.backend.benchmark_service import BenchmarkCache
from studio.backend.tests.test_benchmark_cache import report


def wait_idle(cache, timeout=5.0):
    deadline = time.monotonic() + timeout
    while cache.refreshing and time.monotonic() < deadline:
        time.sleep(0.01)
    return not cache.refreshing


class BenchmarkApiTests(unittest.TestCase):
    def test_read_refresh_and_failure_preserve_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Mock(side_effect=[report(1), report(2), RuntimeError("offline failure")])
            cache = BenchmarkCache(Path(directory) / "report.json", version="test", runner=runner)
            with patch("studio.backend.api.routes.BenchmarkCache", return_value=cache), \
                 patch("studio.backend.api.routes.source_version", return_value="test"):
                app = FastAPI()
                app.include_router(build_router(Mock()))
            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.get("/api/benchmark")
                self.assertEqual(first.status_code, 200)
                # 响应 = 报告本体 + cache 元数据（cached_at / refreshing 标记）
                self.assertEqual(first.json()["dataset"], report(1)["dataset"])
                self.assertFalse(first.json()["cache"]["refreshing"])
                self.assertEqual(client.get("/api/benchmark").json()["cache"]["refreshing"], False)
                self.assertEqual(runner.call_count, 1)
                # 手动刷新：立即返回旧报告 + refreshing 标记；评测在后台完成后可见
                refreshed = client.get("/api/benchmark?refresh=1")
                self.assertEqual(refreshed.status_code, 200)
                self.assertEqual(refreshed.json()["dataset"], report(1)["dataset"])
                self.assertTrue(refreshed.json()["cache"]["refreshing"])
                self.assertTrue(wait_idle(cache))
                self.assertEqual(client.get("/api/benchmark").json()["dataset"],
                                 report(2)["dataset"])

    def test_background_refresh_failure_keeps_last_good_report(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Mock(side_effect=[report(1), RuntimeError("offline failure")])
            cache = BenchmarkCache(Path(directory) / "report.json", version="test", runner=runner)
            with patch("studio.backend.api.routes.BenchmarkCache", return_value=cache), \
                 patch("studio.backend.api.routes.source_version", return_value="test"):
                app = FastAPI()
                app.include_router(build_router(Mock()))
            with TestClient(app, raise_server_exceptions=False) as client:
                client.get("/api/benchmark")
                self.assertEqual(client.get("/api/benchmark?refresh=1").status_code, 200)
                self.assertTrue(wait_idle(cache))
                self.assertEqual(client.get("/api/benchmark").json()["dataset"],
                                 report(1)["dataset"])


if __name__ == "__main__":
    unittest.main()
