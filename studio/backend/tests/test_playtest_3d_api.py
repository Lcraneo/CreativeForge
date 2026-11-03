"""试玩舞台 3D POC-0 后端清单接口回归。

覆盖：
- 离网夹具清单（无 asset_id）与夹具 GLB 伺服；
- 正常 mesh → available=true + 正确 mesh_url；
- 缺 mesh / mesh 失败 / 非 glb 格式 / 路径非法 / 资产不存在 → 明确错误。
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.routes import build_router


def _asset(mesh: dict | None) -> dict:
    asset = {"id": "ast-123", "name": "fixture-char"}
    if mesh is not None:
        asset["extensions"] = {"cloud_backends": {"mesh": mesh}}
    return asset


class Playtest3DManifestTests(unittest.TestCase):
    def _client(self, asset_for_get: dict | None) -> TestClient:
        runtime = Mock()
        runtime.assets.get.return_value = asset_for_get
        runtime.assets.latest.return_value = None
        runtime.history.get.return_value = None
        runtime.history.list.return_value = []
        app = FastAPI()
        app.include_router(build_router(runtime))
        return TestClient(app)

    def test_fixture_manifest_without_asset(self):
        client = self._client(None)
        resp = client.get("/api/playtest/3d")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["asset_id"], "playtest3d-fixture")
        self.assertEqual(body["mesh_url"], "/api/playtest/3d/fixture.glb")
        self.assertEqual(len(body["clips"]), 5)
        self.assertTrue(any(c["name"] == "idle" and c["loop"] for c in body["clips"]))
        self.assertTrue(any(c["name"] == "jump" and not c["loop"] for c in body["clips"]))

    def test_fixture_glb_served(self):
        client = self._client(None)
        resp = client.get("/api/playtest/3d/fixture.glb")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content)
        self.assertIn(resp.headers["content-type"], ("model/gltf-binary", "application/octet-stream"))

    def test_succeeded_mesh_returns_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            mesh_rel = "artifacts/ast-123/mesh.glb"
            os.makedirs(os.path.join(tmp, "artifacts", "ast-123"), exist_ok=True)
            with open(os.path.join(tmp, "artifacts", "ast-123", "mesh.glb"), "wb") as handle:
                handle.write(b"gltf-binary")
            mesh = {"status": "succeeded", "provider": "bailian-tripo", "format": "glb",
                    "local_path": mesh_rel, "bytes": 11, "sha256": "ab" * 32, "rigged": False}
            with patch.dict(os.environ, {"CF_CLOUD_CACHE_DIR": tmp}):
                client = self._client(_asset(mesh))
                resp = client.get("/api/playtest/3d?asset_id=ast-123")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["available"])
                self.assertIsNone(body["error"])
                self.assertEqual(body["mesh_url"], "/api/cloud/artifacts/artifacts/ast-123/mesh.glb")
                self.assertEqual(body["bytes"], 11)
                self.assertEqual(body["rig"]["rigged"], False)
                self.assertIn("ast-123", body["fallback_url"])

    def test_missing_mesh(self):
        client = self._client(_asset(None))
        body = client.get("/api/playtest/3d?asset_id=ast-123").json()
        self.assertFalse(body["available"])
        self.assertEqual(body["error"], "mesh_missing")
        self.assertIsNone(body["mesh_url"])

    def test_failed_mesh(self):
        mesh = {"status": "failed", "error_class": "server", "error_message": "boom"}
        client = self._client(_asset(mesh))
        body = client.get("/api/playtest/3d?asset_id=ast-123").json()
        self.assertEqual(body["error"], "mesh_failed")

    def test_unsupported_format(self):
        mesh = {"status": "succeeded", "provider": "meshy", "format": "obj",
                "local_path": "artifacts/ast-123/mesh.obj"}
        client = self._client(_asset(mesh))
        body = client.get("/api/playtest/3d?asset_id=ast-123").json()
        self.assertEqual(body["error"], "unsupported_format")

    def test_path_traversal_rejected(self):
        mesh = {"status": "succeeded", "provider": "meshy", "format": "glb",
                "local_path": "../evil.glb"}
        client = self._client(_asset(mesh))
        body = client.get("/api/playtest/3d?asset_id=ast-123").json()
        self.assertEqual(body["error"], "path_invalid")

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mesh = {"status": "succeeded", "provider": "meshy", "format": "glb",
                    "local_path": "artifacts/ast-123/does-not-exist.glb"}
            with patch.dict(os.environ, {"CF_CLOUD_CACHE_DIR": tmp}):
                client = self._client(_asset(mesh))
                body = client.get("/api/playtest/3d?asset_id=ast-123").json()
                self.assertEqual(body["error"], "path_invalid")

    def test_asset_not_found(self):
        client = self._client(None)
        body = client.get("/api/playtest/3d?asset_id=missing-id").json()
        self.assertFalse(body["available"])
        self.assertEqual(body["error"], "asset_not_found")


if __name__ == "__main__":
    unittest.main()