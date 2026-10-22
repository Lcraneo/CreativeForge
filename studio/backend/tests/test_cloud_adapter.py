"""S3/S4 回归：四个算子、适配器契约、厂商工厂与云路由。

覆盖实施计划 S3「适配」与 S4「产品面」中可离线验证的部分：

- 四个槽位（mesh / image / video / audio）的成功写回与失败留痕（R7）
- ``CloudAssetAdapter`` 的导入 / 导出净化（R8）、路径沙箱（R5）与缓存维护
- ``build_model`` 的厂商分派、``probe`` 的错误分类
- 云路由的开关旁路（``CF_CLOUD_BACKENDS=off``）、同步/异步语义与产物伺服

全部用例使用临时缓存目录与假 wrapper，不发起真实网络请求。

运行：``python -m unittest studio.backend.tests.test_cloud_adapter -v``
"""

import os
import tempfile
import time
import unittest
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapters.cloud_backends import config as cloud_config
from adapters.cloud_backends import providers as cloud_providers
from adapters.cloud_backends.client import cloud_client
from adapters.cloud_backends.cloud_adapter import CloudAssetAdapter
from adapters.cloud_backends.contracts import extension_v1 as contract
from adapters.cloud_backends.operators import audio, cg_video, image, object_3d
from studio.backend.api.cloud_routes import build_cloud_router
from studio.backend.api.cloud_settings_routes import build_cloud_settings_router
from studio.backend.cloud_service.provider_store import CloudProviderStore
from studio.backend.cloud_service.usage import CloudUsageLedger


class FakeModel:
    """最小 wrapper：写固定字节，可注入一次异常。"""

    PROVIDER = "ark"
    model = "fake-model"
    OUTPUT_EXT = "glb"

    def __init__(self, data: bytes = b"fake-bytes", error: Exception | None = None):
        self.data = data
        self.error = error
        self.calls: list[dict] = []
        self.closed = False
        self.last_call_info: dict = {}

    def infer_and_save(self, output_path: str, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        with open(output_path, "wb") as handle:
            handle.write(self.data)
        self.last_call_info = {"cache_key": "hash-1", "cached": False, "credits": 2}
        return output_path

    def close(self) -> None:
        self.closed = True


def _asset() -> dict:
    return {"id": "asset-1", "identity": {"name": "knight"}, "version": {"schema": "1.0"}}


def _slot(asset: dict, slot: str) -> dict:
    block = contract.read_extension(asset) or {}
    return block.get(slot) or {}


class _TempCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"CF_CLOUD_CACHE_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


# ── 算子 ────────────────────────────────────────────────────────────────────


class OperatorTests(_TempCache):
    def test_image_success_writes_contract_slot(self):
        asset = _asset()
        model = FakeModel()

        slot = image.generate(asset, model, prompt="a knight", size="512x768", seed=7)

        self.assertEqual(slot["status"], "succeeded")
        self.assertEqual(slot["provider"], "ark")
        self.assertEqual(slot["width"], 512)
        self.assertEqual(slot["height"], 768)
        self.assertTrue(slot["local_path"].startswith("artifacts/"))
        self.assertEqual(slot["bytes"], len(b"fake-bytes"))
        self.assertEqual(len(slot["sha256"]), 64)
        self.assertTrue(os.path.isfile(contract.resolve_local_path(slot["local_path"])))
        self.assertEqual(_slot(asset, "image")["status"], "succeeded")
        provenance = contract.read_extension(asset)["provenance"]
        self.assertEqual(provenance["request_hash"], "hash-1")
        self.assertEqual(provenance["credits_estimate"], 2)

    def test_image_without_prompt_leaves_failure_footprint(self):
        asset = _asset()
        slot = image.generate(asset, FakeModel(), prompt="   ")
        self.assertEqual(slot["status"], "failed")
        self.assertEqual(slot["error_class"], "invalid_request")

    def test_audio_dialogue_and_unknown_kind(self):
        asset = _asset()
        slot = audio.generate(asset, FakeModel(), kind="dialogue", text="你好")
        self.assertEqual(slot["status"], "succeeded")
        self.assertEqual(slot["kind"], "dialogue")

        broken = audio.generate(asset, FakeModel(), kind="music", text="x")
        self.assertEqual(broken["status"], "failed")
        self.assertEqual(broken["error_class"], "invalid_request")

    def test_video_requires_prompt_or_image(self):
        asset = _asset()
        slot = cg_video.generate(asset, FakeModel(), prompt=None)
        self.assertEqual(slot["status"], "failed")
        self.assertEqual(slot["error_class"], "invalid_request")

        ok = cg_video.generate(asset, FakeModel(), prompt="camera pan", duration=4)
        self.assertEqual(ok["status"], "succeeded")
        self.assertEqual(ok["duration_s"], 4.0)

    def test_mesh_uses_wrapper_output_extension(self):
        asset = _asset()
        model = FakeModel()
        model.OUTPUT_EXT = "glb"
        slot = object_3d.generate(asset, model, prompt="a sword")
        self.assertEqual(slot["status"], "succeeded")
        self.assertEqual(slot["format"], "glb")
        self.assertTrue(slot["local_path"].endswith(".glb"))

    def test_cloud_error_class_is_preserved(self):
        asset = _asset()
        model = FakeModel(error=cloud_client.CloudAPIQuotaError("额度耗尽", provider="ark"))
        slot = image.generate(asset, model, prompt="x")
        self.assertEqual(slot["status"], "failed")
        self.assertEqual(slot["error_class"], "quota")


# ── 适配器 ──────────────────────────────────────────────────────────────────


class AdapterTests(_TempCache):
    def test_import_from_bytes_then_export_strips_provenance(self):
        adapter = CloudAssetAdapter()
        asset = _asset()
        slot = adapter.import_asset(
            {"asset": asset, "slot": "image", "provider": "ark", "bytes": b"png", "ext": "png"}
        )
        self.assertEqual(slot["status"], "succeeded")
        self.assertEqual(_slot(asset, "image")["provider"], "ark")

        view = adapter.export_asset(asset)
        self.assertEqual(view["slots"]["image"]["status"], "succeeded")
        self.assertNotIn("provenance", view["slots"])
        self.assertEqual(len(view["files"]), 1)
        self.assertTrue(view["files"][0]["exists"])

    def test_import_rejects_unknown_provider_and_missing_payload(self):
        adapter = CloudAssetAdapter()
        with self.assertRaises(contract.CloudExtensionError):
            adapter.import_asset({"asset": _asset(), "slot": "image", "provider": "nope", "bytes": b"x"})
        with self.assertRaises(contract.CloudExtensionError):
            adapter.import_asset({"asset": _asset(), "slot": "image", "provider": "ark"})
        with self.assertRaises(contract.CloudExtensionError):
            adapter.import_asset({"asset": _asset(), "slot": "voice", "provider": "ark", "bytes": b"x"})

    def test_path_sandbox_and_cache_maintenance(self):
        self.assertIsNone(contract.safe_rel_path("../escape.png"))
        self.assertIsNone(contract.safe_rel_path("C:/Windows/win.ini"))

        adapter = CloudAssetAdapter()
        self.assertTrue(adapter.can_handle("image"))
        self.assertFalse(adapter.can_handle("unknown"))

        asset = _asset()
        adapter.import_asset(
            {"asset": asset, "slot": "video", "provider": "ark", "bytes": b"mp4", "ext": "mp4"}
        )
        stats = adapter.cache_stats()
        self.assertGreaterEqual(stats["files"], 1)
        self.assertGreaterEqual(stats["bytes"], 3)
        self.assertEqual(stats["max_bytes"], cloud_config.cache_max_bytes())

        self.assertGreaterEqual(adapter.clear_cache(), 1)
        self.assertFalse(adapter.export_asset(asset)["files"][0]["exists"])


# ── 厂商工厂 / 探测 ─────────────────────────────────────────────────────────


class ProviderFactoryTests(unittest.TestCase):
    def test_build_model_dispatch(self):
        from adapters.cloud_backends.models.bailian_tripo import BailianTripoModel
        from adapters.cloud_backends.models.meshy import MeshyModel
        from adapters.cloud_backends.models.seed_audio import SeedAudioModel
        from adapters.cloud_backends.models.seedance import SeedanceModel
        from adapters.cloud_backends.models.seedream import SeedreamModel
        from adapters.cloud_backends.models.tripo import TripoOfficialModel

        cases = [
            ("bailian-tripo", "gen_3d_object_cloud", BailianTripoModel),
            ("tripo", "gen_3d_object_cloud", TripoOfficialModel),
            ("meshy", "gen_3d_object_cloud", MeshyModel),
            ("ark", "gen_image_cloud", SeedreamModel),
            ("ark", "gen_cg_video_cloud", SeedanceModel),
            ("seed-audio", "gen_audio_cloud", SeedAudioModel),
        ]
        for provider, capability, expected in cases:
            with self.subTest(provider=provider, capability=capability):
                model = cloud_providers.build_model(provider, capability=capability, api_key="k")
                self.assertIsInstance(model, expected)
                model.close()

        with self.assertRaises(ValueError):
            cloud_providers.build_model("unknown", api_key="k")

    def test_probe_classifies_endpoint_status(self):
        ok = cloud_providers.probe(
            "tripo",
            api_base="https://example.test",
            api_key="k",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )
        self.assertTrue(ok["ok"])

        denied = cloud_providers.probe(
            "tripo",
            api_base="https://example.test",
            api_key="k",
            transport=httpx.MockTransport(lambda request: httpx.Response(401)),
        )
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["status"], 401)

        missing = cloud_providers.probe("tripo", api_base="")
        self.assertFalse(missing["ok"])


# ── 云路由 ──────────────────────────────────────────────────────────────────


class CloudRouteTests(_TempCache):
    def setUp(self):
        super().setUp()
        runtime = mock.Mock()
        runtime.assets.get.return_value = None
        runtime.assets.save.return_value = None
        runtime.history.get.return_value = None
        runtime.history.list.return_value = []
        runtime.model_settings.effective.return_value = {}
        self.store = CloudProviderStore(
            path=os.path.join(self._tmp.name, "providers.json"),
            secret_file=os.path.join(self._tmp.name, ".secret"),
            settings_provider=lambda: {},
        )
        usage_path = os.path.join(self._tmp.name, "usage.json")
        with mock.patch(
            "studio.backend.api.cloud_routes.CloudUsageLedger",
            lambda: CloudUsageLedger(usage_path),
        ), mock.patch(
            "studio.backend.api.cloud_settings_routes.CloudUsageLedger",
            lambda: CloudUsageLedger(usage_path),
        ):
            app = FastAPI()
            app.include_router(build_cloud_router(runtime, self.store))
            app.include_router(build_cloud_settings_router(runtime, self.store))
        self.client = TestClient(app)
        self.models: list[FakeModel] = []

        def factory(*args, **kwargs):
            model = FakeModel()
            self.models.append(model)
            return model

        self._patch = mock.patch(
            "studio.backend.api.cloud_routes.cloud_providers.build_model",
            side_effect=factory,
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        super().tearDown()

    def test_image_sync_route_and_artifact_serving(self):
        response = self.client.post("/api/cloud/image", json={"prompt": "a knight"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "succeeded")
        self.assertEqual(body["provider"], "ark")
        self.assertEqual(body["attempts"][0]["status"], "succeeded")

        served = self.client.get(f"/api/cloud/artifacts/{body['local_path']}")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.content, b"fake-bytes")

    def test_image_route_failure_returns_502_with_class(self):
        self._patch.stop()
        failed = FakeModel(error=cloud_client.CloudAPIAuthError("bad key", provider="ark"))
        self._patch = mock.patch(
            "studio.backend.api.cloud_routes.cloud_providers.build_model",
            return_value=failed,
        )
        self._patch.start()
        response = self.client.post("/api/cloud/image", json={"prompt": "a knight"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("auth:", response.json()["detail"])

    def test_disabled_switch_is_a_hard_bypass(self):
        with mock.patch.dict(os.environ, {"CF_CLOUD_BACKENDS": "off"}):
            self.assertEqual(
                self.client.post("/api/cloud/image", json={"prompt": "x"}).status_code, 503
            )
            self.assertEqual(
                self.client.post("/api/cloud/3d", json={"prompt": "x"}).status_code, 503
            )
            listed = self.client.get("/api/cloud/providers")
            self.assertEqual(listed.status_code, 200)
            self.assertFalse(listed.json()["enabled"])

    def test_3d_async_route_completes(self):
        response = self.client.post("/api/cloud/3d", json={"prompt": "a sword"})
        self.assertEqual(response.status_code, 202)
        task_id = response.json()["task_id"]

        deadline = time.time() + 5
        snapshot = {}
        while time.time() < deadline:
            snapshot = self.client.get(f"/api/cloud/3d/{task_id}").json()
            if snapshot["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.02)

        self.assertEqual(snapshot["status"], "succeeded")
        self.assertEqual(snapshot["result"]["status"], "succeeded")
        self.assertEqual(snapshot["result"]["attempts"][0]["provider"], "bailian-tripo")
        self.assertEqual(self.client.get("/api/cloud/3d/unknown").status_code, 404)

    def test_settings_routes_configure_and_mask(self):
        listed = self.client.get("/api/settings/cloud/providers")
        self.assertEqual(listed.status_code, 200)
        self.assertIn("ark", [item["id"] for item in listed.json()["providers"]])

        saved = self.client.put(
            "/api/settings/cloud/providers/ark",
            json={"model": "doubao-seedream-4-0-250828"},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["model"], "doubao-seedream-4-0-250828")

        keyed = self.client.put(
            "/api/settings/cloud/providers/ark/key", json={"api_key": "sk-test-123456"}
        )
        self.assertEqual(keyed.status_code, 200)
        self.assertTrue(keyed.json()["has_key"])
        self.assertNotIn("sk-test-123456", keyed.text)
        self.assertIn("***", keyed.json()["key_hint"])

        self.assertEqual(
            self.client.put("/api/settings/cloud/providers/nope", json={}).status_code, 404
        )
        self.assertEqual(self.client.get("/api/settings/cloud/usage").status_code, 200)

    def test_audio_route_validation(self):
        self.assertEqual(self.client.post("/api/cloud/audio", json={}).status_code, 422)
        response = self.client.post("/api/cloud/audio", json={"text": "你好", "kind": "dialogue"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
