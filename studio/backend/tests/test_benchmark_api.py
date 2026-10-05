"""Exercise the real FastAPI route with an offline evaluator and temporary cache."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.routes import build_router
from studio.backend.benchmark_service import BenchmarkCache
from studio.backend.tests.test_benchmark_cache import report


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
                self.assertEqual(first.json(), report(1))
                self.assertEqual(client.get("/api/benchmark").json(), report(1))
                self.assertEqual(runner.call_count, 1)
                refreshed = client.get("/api/benchmark?refresh=1")
                self.assertEqual(refreshed.status_code, 200)
                self.assertEqual(refreshed.json(), report(2))
                self.assertEqual(client.get("/api/benchmark?refresh=1").status_code, 500)
                self.assertEqual(client.get("/api/benchmark").json(), report(2))


if __name__ == "__main__":
    unittest.main()
