"""S2 内核回归：云管道重试/错误分类/缓存/下载限额，以及三条 3D 通道的协议解析。

全部离线运行：HTTP 层用 ``httpx.MockTransport`` 拦掉，休眠用空实现，
因此测试不需要网络、凭据或真实计费。

运行：``python -m unittest studio.backend.tests.test_cloud_client -v``
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import httpx

from adapters.cloud_backends.client import cloud_client
from adapters.cloud_backends.contracts import extension_v1 as contract
from adapters.cloud_backends.models.bailian_tripo import BailianTripoModel
from adapters.cloud_backends.models.meshy import MeshyModel
from adapters.cloud_backends.models.tripo import TripoOfficialModel

NO_SLEEP = lambda _seconds: None  # noqa: E731 - 测试用空休眠

GLB_BYTES = b"glTF" + b"\x00" * 64


def _transport(handler, calls: list | None = None) -> httpx.MockTransport:
    """包装 handler，顺便记录每次请求（method, url, headers, body）。"""

    def wrapped(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped)


def _json_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


class CloudClientTests(unittest.TestCase):
    def _client(self, transport) -> cloud_client.CloudAPIClient:
        return cloud_client.CloudAPIClient(
            "https://api.example.com",
            "test-key",
            provider="test",
            max_retries=2,
            backoff=0.0,
            transport=transport,
            sleep=NO_SLEEP,
        )

    # 错误分类 ────────────────────────────────────────────────────────────
    def test_auth_error_is_terminal(self):
        calls: list = []
        client = self._client(
            _transport(lambda _r: _json_response({"message": "bad key"}, 401), calls)
        )
        with self.assertRaises(cloud_client.CloudAPIAuthError) as ctx:
            client.request("GET", "/x")
        self.assertEqual(ctx.exception.error_class, "auth")
        self.assertEqual(len(calls), 1)  # 终态错误不重试

    def test_quota_error_is_terminal(self):
        calls: list = []
        client = self._client(
            _transport(lambda _r: _json_response({"message": "no credits"}, 402), calls)
        )
        with self.assertRaises(cloud_client.CloudAPIQuotaError) as ctx:
            client.request("GET", "/x")
        self.assertEqual(ctx.exception.error_class, "quota")
        self.assertEqual(len(calls), 1)

    def test_invalid_request_is_terminal(self):
        client = self._client(_transport(lambda _r: _json_response({}, 400)))
        with self.assertRaises(cloud_client.CloudAPIRequestError) as ctx:
            client.request("GET", "/x")
        self.assertEqual(ctx.exception.error_class, "invalid_request")

    def test_rate_limit_retries_then_succeeds(self):
        calls: list = []
        state = {"n": 0}

        def handler(_request):
            state["n"] += 1
            if state["n"] == 1:
                return _json_response({"message": "slow down"}, 429)
            return _json_response({"ok": True})

        client = self._client(_transport(handler, calls))
        self.assertEqual(client.request("GET", "/x"), {"ok": True})
        self.assertEqual(len(calls), 2)

    def test_server_error_exhausts_retries(self):
        calls: list = []
        client = self._client(
            _transport(lambda _r: _json_response({"message": "boom"}, 503), calls)
        )
        with self.assertRaises(cloud_client.CloudAPIServerError) as ctx:
            client.request("GET", "/x")
        self.assertEqual(ctx.exception.error_class, "server")
        self.assertEqual(len(calls), 3)  # 首次 + 2 次重试

    def test_transport_error_is_retryable(self):
        calls: list = []
        state = {"n": 0}

        def handler(request):
            state["n"] += 1
            if state["n"] == 1:
                raise httpx.ConnectError("refused", request=request)
            return _json_response({"ok": 1})

        client = self._client(_transport(handler, calls))
        self.assertEqual(client.request("GET", "/x"), {"ok": 1})

    def test_non_json_success_raises(self):
        client = self._client(_transport(lambda _r: httpx.Response(200, text="<html>oops</html>")))
        with self.assertRaises(cloud_client.CloudAPIError):
            client.request("GET", "/x")

    # 下载 ────────────────────────────────────────────────────────────────
    def test_download_respects_max_bytes(self):
        big = b"x" * 4096
        client = self._client(_transport(lambda _r: httpx.Response(200, content=big)))
        with self.assertRaises(cloud_client.CloudAPIError) as ctx:
            client.download("https://cdn.example.com/a.glb", max_bytes=1024)
        self.assertIn("上限", str(ctx.exception))

    def test_download_success(self):
        client = self._client(_transport(lambda _r: httpx.Response(200, content=GLB_BYTES)))
        self.assertEqual(client.download("https://cdn.example.com/a.glb"), GLB_BYTES)

    def test_download_404_is_terminal(self):
        client = self._client(_transport(lambda _r: httpx.Response(404, text="gone")))
        with self.assertRaises(cloud_client.CloudAPIRequestError):
            client.download("https://cdn.example.com/a.glb")

    # 哈希 ────────────────────────────────────────────────────────────────
    def test_request_hash_ignores_none_and_is_order_free(self):
        first = cloud_client.request_hash({"a": 1, "b": None, "c": [1, 2]})
        second = cloud_client.request_hash({"c": [1, 2], "a": 1})
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("sha256:"))
        self.assertNotEqual(first, cloud_client.request_hash({"a": 2, "c": [1, 2]}))

    def test_error_class_values_all_known_to_contract(self):
        """异常分类必须与契约 ERROR_CLASSES 完全对齐，否则失败槽位写不进去。"""

        classes = {
            cloud_client.CloudAPIAuthError.error_class,
            cloud_client.CloudAPIQuotaError.error_class,
            cloud_client.CloudAPIRequestError.error_class,
            cloud_client.CloudAPIServerError.error_class,
            cloud_client.CloudAPIRateLimitError.error_class,
            cloud_client.CloudTaskFailed.error_class,
            cloud_client.CloudTaskTimeout.error_class,
        }
        self.assertTrue(classes.issubset(set(contract.ERROR_CLASSES)), classes)
        for name in classes:
            slot = contract.error_slot("tripo", name, "x")
            self.assertEqual(contract.validate({"version": "1.0", "mesh": slot}), [])


class PollTaskTests(unittest.TestCase):
    def test_poll_returns_on_done_state(self):
        states = iter(["PENDING", "RUNNING", "SUCCEEDED"])
        task = cloud_client.poll_task(
            lambda: {"output": {"task_status": next(states)}},
            task_id="t1",
            poll_interval=0.0,
            sleep=NO_SLEEP,
        )
        self.assertEqual(task["output"]["task_status"], "SUCCEEDED")

    def test_poll_raises_task_failed(self):
        with self.assertRaises(cloud_client.CloudTaskFailed) as ctx:
            cloud_client.poll_task(
                lambda: {"output": {"task_status": "FAILED", "message": "bad input"}},
                task_id="t2",
                sleep=NO_SLEEP,
            )
        self.assertEqual(ctx.exception.error_class, "task_failed")
        self.assertIn("bad input", str(ctx.exception))

    def test_poll_timeout_keeps_task_id(self):
        clock = {"t": 0.0}

        def now():
            clock["t"] += 100.0
            return clock["t"]

        with self.assertRaises(cloud_client.CloudTaskTimeout) as ctx:
            cloud_client.poll_task(
                lambda: {"output": {"task_status": "RUNNING"}},
                task_id="t3",
                timeout=50.0,
                sleep=NO_SLEEP,
                now=now,
            )
        self.assertEqual(ctx.exception.error_class, "task_timeout")
        self.assertEqual(ctx.exception.task_id, "t3")

    def test_poll_rejects_non_dict(self):
        with self.assertRaises(cloud_client.CloudAPIError):
            cloud_client.poll_task(lambda: ["nope"], task_id="t4", sleep=NO_SLEEP)


class ResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = cloud_client.ResponseCache(
            self.directory.name, "test", ttl_seconds=3600, max_bytes=4096
        )

    def test_roundtrip(self):
        key = cloud_client.request_hash({"a": 1})
        self.assertIsNone(self.cache.get(key, ext="glb"))
        self.cache.put(key, GLB_BYTES, ext="glb")
        self.assertEqual(self.cache.get(key, ext="glb"), GLB_BYTES)

    def test_ttl_expiry(self):
        key = cloud_client.request_hash({"a": 1})
        expired = cloud_client.ResponseCache(
            self.directory.name, "test", ttl_seconds=1, max_bytes=4096
        )
        expired.put(key, GLB_BYTES, ext="glb")
        path = expired._path(key, "glb")
        os.utime(path, (0, 0))  # 人为置为很久以前
        self.assertIsNone(expired.get(key, ext="glb"))

    def test_evicts_when_over_limit(self):
        small = cloud_client.ResponseCache(
            self.directory.name, "evict", ttl_seconds=0, max_bytes=1024
        )
        for index in range(4):
            key = cloud_client.request_hash({"i": index})
            small.put(key, b"y" * 512, ext="bin")
            path = small._path(key, "bin")
            os.utime(path, (index + 1, index + 1))  # 保证删除顺序可预期

        names = [
            os.path.join(root, name) for root, _, files in os.walk(small.root) for name in files
        ]
        total = sum(os.path.getsize(path) for path in names)
        self.assertLessEqual(total, 1024)  # 写入即自动清理，始终不超上限
        self.assertLess(len(names), 4)

    def test_evict_counts_expired_entries(self):
        # 先用不过期的实例落盘，再换短 TTL 实例触发清理
        cache = cloud_client.ResponseCache(
            self.directory.name, "ttl", ttl_seconds=0, max_bytes=1 << 20
        )
        for index in range(2):
            key = cloud_client.request_hash({"t": index})
            cache.put(key, b"z" * 32, ext="bin")
            os.utime(cache._path(key, "bin"), (0, 0))
        expired = cloud_client.ResponseCache(
            self.directory.name, "ttl", ttl_seconds=1, max_bytes=1 << 20
        )
        self.assertEqual(expired.evict(), 2)


class BailianTripoTests(unittest.TestCase):
    """百炼 Tripo：创建 → 轮询 → 下载，两段式异步协议。"""

    BASE = "https://ws-test.cn-beijing.maas.aliyuncs.com"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.calls: list = []

    def _model(self, handler, **kwargs) -> BailianTripoModel:
        return BailianTripoModel(
            api_key="test-key",
            api_base=self.BASE,
            workspace_id="ws-test",
            cache_dir=self.directory.name,
            task_timeout=60.0,
            poll_interval=0.0,
            backoff=0.0,
            transport=_transport(handler, self.calls),
            sleep=NO_SLEEP,
            **kwargs,
        )

    @staticmethod
    def _happy_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/3d-generation"):
            return _json_response({"output": {"task_status": "PENDING", "task_id": "task-1"}})
        if request.url.path.endswith("/tasks/task-1"):
            return _json_response(
                {
                    "output": {"task_status": "SUCCEEDED", "task_id": "task-1"},
                    "usage": {"3d_task_type": "text-to-3D"},
                    "results": [
                        {
                            "pbr_model_url": "https://cdn.example.com/a.glb",
                            "rendered_image_url": "https://cdn.example.com/a.png",
                        }
                    ],
                }
            )
        return httpx.Response(200, content=GLB_BYTES)

    def test_full_flow_sends_async_header_and_parses_result(self):
        model = self._model(self._happy_handler)
        data = model.infer(prompt="一只可爱的猫", seed=42, decimation_target=30000)

        self.assertEqual(data, GLB_BYTES)
        create = self.calls[0]
        self.assertEqual(create.headers.get("x-dashscope-async"), "enable")
        body = json.loads(create.content)
        self.assertEqual(body["model"], "Tripo/Tripo-H3.1")
        self.assertEqual(body["input"]["prompt"], "一只可爱的猫")
        self.assertEqual(body["parameters"]["texture_quality"], "standard")
        # 接口无对应参数：必须记录而不发送
        self.assertNotIn("seed", json.dumps(body))
        self.assertEqual(model.last_call_info["ignored_params"], ["decimation_target", "seed"])
        self.assertEqual(model.last_call_info["task_type"], "text-to-3D")
        self.assertTrue(model.last_call_info["preview_url"].endswith("a.png"))

    def test_second_call_hits_cache_without_http(self):
        model = self._model(self._happy_handler)
        first = model.infer(prompt="猫")
        after_first = len(self.calls)
        second = model.infer(prompt="猫")

        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), after_first)  # 完全命中缓存，无新请求
        self.assertTrue(model.last_call_info["cached"])
        self.assertTrue(model.last_call_info["cache_key"].startswith("sha256:"))

    def test_missing_workspace_id_reports_actionable_error(self):
        model = BailianTripoModel(
            api_key="test-key",
            api_base="https://{workspace_id}.cn-beijing.maas.aliyuncs.com",
            cache_dir=self.directory.name,
            transport=_transport(self._happy_handler, self.calls),
            sleep=NO_SLEEP,
        )
        with self.assertRaises(cloud_client.CloudAPIRequestError) as ctx:
            model.infer(prompt="猫")
        self.assertIn("workspace_id", str(ctx.exception))
        self.assertEqual(len(self.calls), 0)  # 本地就拦住了，没发请求

    def test_local_image_without_uploader_is_rejected(self):
        model = self._model(self._happy_handler)
        with self.assertRaises(cloud_client.CloudAPIRequestError) as ctx:
            model.infer(image=b"PNGDATA")
        self.assertIn("公网", str(ctx.exception))

    def test_uploader_is_used_for_local_image(self):
        uploaded: list = []

        def uploader(data: bytes, name: str) -> str:
            uploaded.append((data, name))
            return "https://oss.example.com/uploaded.png"

        model = self._model(self._happy_handler, uploader=uploader)
        model.infer(image=b"PNGDATA", image_name="hero.png")

        self.assertEqual(uploaded, [(b"PNGDATA", "hero.png")])
        body = json.loads(self.calls[0].content)
        self.assertEqual(body["input"]["image"], "https://oss.example.com/uploaded.png")

    def test_failed_task_maps_to_task_failed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/3d-generation"):
                return _json_response({"output": {"task_id": "task-2"}})
            return _json_response(
                {
                    "output": {"task_status": "FAILED", "task_id": "task-2"},
                    "results": [{"code": "InvalidParameter", "message": "图片不可用"}],
                }
            )

        model = self._model(handler)
        with self.assertRaises(cloud_client.CloudAPIError) as ctx:
            model.infer(prompt="猫")
        self.assertIn("图片不可用", str(ctx.exception))

    def test_missing_task_id_raises(self):
        model = self._model(lambda _r: _json_response({"output": {}}))
        with self.assertRaises(cloud_client.CloudAPIError) as ctx:
            model.infer(prompt="猫")
        self.assertIn("task_id", str(ctx.exception))

    def test_missing_api_key_raises_auth_error(self):
        model = BailianTripoModel(
            api_base=self.BASE,
            workspace_id="ws-test",
            cache_dir=self.directory.name,
            transport=_transport(self._happy_handler),
            sleep=NO_SLEEP,
        )
        saved = os.environ.pop("DASHSCOPE_API_KEY", None)
        self.addCleanup(lambda: saved and os.environ.__setitem__("DASHSCOPE_API_KEY", saved))
        with self.assertRaises(cloud_client.CloudAPIAuthError) as ctx:
            model.infer(prompt="猫")
        self.assertIn("DASHSCOPE_API_KEY", str(ctx.exception))

    def test_infer_and_save_writes_file(self):
        model = self._model(self._happy_handler)
        target = Path(self.directory.name) / "out" / "hero.glb"
        path = model.infer_and_save(str(target), prompt="猫")
        self.assertEqual(Path(path).read_bytes(), GLB_BYTES)


class TripoOfficialTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.calls: list = []

    def _model(self, handler, **kwargs) -> TripoOfficialModel:
        return TripoOfficialModel(
            api_key="test-key",
            api_base="https://openapi.tripo3d.ai/v3",
            cache_dir=self.directory.name,
            poll_interval=0.0,
            backoff=0.0,
            transport=_transport(handler, self.calls),
            sleep=NO_SLEEP,
            **kwargs,
        )

    def test_uploads_local_image_and_downloads_glb(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/files"):
                return _json_response({"code": 0, "data": {"file_token": "ft-1"}})
            if path.endswith("/generation/image-to-model"):
                return _json_response({"code": 0, "data": {"task_id": "tk-1"}})
            if "/tasks/" in path:
                return _json_response(
                    {
                        "code": 0,
                        "data": {
                            "task_id": "tk-1",
                            "status": "success",
                            "output": {"model_url": "https://cdn.example.com/a.glb"},
                            "credits_consumed": 20,
                        },
                    }
                )
            return httpx.Response(200, content=GLB_BYTES)

        model = self._model(handler)
        data = model.infer(image=b"PNGDATA", seed=7)

        self.assertEqual(data, GLB_BYTES)
        # 第一步必须是上传换 token
        self.assertTrue(self.calls[0].url.path.endswith("/files"))
        body = json.loads(self.calls[1].content)
        self.assertEqual(body["input"], "ft-1")
        self.assertEqual(body["model_seed"], 7)
        self.assertEqual(model.last_call_info["credits"], 20)

    def test_nonzero_code_is_terminal(self):
        calls: list = []

        def handler(_request):
            return _json_response({"code": 1004, "message": "auth failed"})

        model = TripoOfficialModel(
            api_key="k",
            api_base="https://openapi.tripo3d.ai/v3",
            cache_dir=self.directory.name,
            max_retries=2,
            transport=_transport(handler, calls),
            sleep=NO_SLEEP,
        )
        with self.assertRaises(cloud_client.CloudAPIRequestError) as ctx:
            model.infer(prompt="cat")
        self.assertIn("1004", str(ctx.exception))
        self.assertEqual(len(calls), 1)  # 终态错误不重试

    def test_face_limit_clamped_when_low_poly(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/text-to-model"):
                captured.update(json.loads(request.content))
                return _json_response({"code": 0, "data": {"task_id": "tk-2"}})
            if "/tasks/" in request.url.path:
                return _json_response(
                    {
                        "code": 0,
                        "data": {
                            "status": "success",
                            "output": {"model_url": "https://cdn.example.com/b.glb"},
                        },
                    }
                )
            return httpx.Response(200, content=GLB_BYTES)

        model = self._model(handler, low_poly=True)
        model.infer(prompt="cat", decimation_target=1_000_000)
        self.assertEqual(captured["face_limit"], 20_000)
        self.assertTrue(captured["smart_low_poly"])


class MeshyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.calls: list = []

    def _model(self, handler, **kwargs) -> MeshyModel:
        return MeshyModel(
            api_key="test-key",
            api_base="https://api.meshy.ai",
            cache_dir=self.directory.name,
            poll_interval=0.0,
            backoff=0.0,
            transport=_transport(handler, self.calls),
            sleep=NO_SLEEP,
            **kwargs,
        )

    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _json_response({"result": "ms-1"})
        if "/image-to-3d/" in request.url.path or "/text-to-3d/" in request.url.path:
            return _json_response(
                {
                    "id": "ms-1",
                    "status": "SUCCEEDED",
                    "model_urls": {"glb": "https://cdn.example.com/m.glb"},
                    "credits_consumed": 25,
                    "thumbnail_url": "https://cdn.example.com/m.png",
                }
            )
        return httpx.Response(200, content=GLB_BYTES)

    def test_image_input_uses_data_uri(self):
        model = self._model(self._handler)
        data = model.infer(image=b"PNGDATA")
        self.assertEqual(data, GLB_BYTES)
        body = json.loads(self.calls[0].content)
        self.assertTrue(body["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(model.last_call_info["credits"], 25)
        self.assertIn("CC BY 4.0", model.last_call_info["license_note"])

    def test_polycount_clamped(self):
        model = self._model(self._handler)
        model.infer(image=b"PNGDATA", decimation_target=1_000_000)
        body = json.loads(self.calls[0].content)
        self.assertEqual(body["target_polycount"], 300_000)

    def test_missing_format_reports_available(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return _json_response({"result": "ms-2"})
            return _json_response(
                {"id": "ms-2", "status": "SUCCEEDED", "model_urls": {"glb": "https://x/y"}}
            )

        model = self._model(handler, output_format="fbx")
        with self.assertRaises(cloud_client.CloudAPIError) as ctx:
            model.infer(image=b"PNGDATA")
        self.assertIn("glb", str(ctx.exception))

    def test_negative_prompt_rejected_locally(self):
        model = self._model(self._handler)
        with self.assertRaises(ValueError):
            model.infer(prompt="cat", negative_prompt="blurry")
        self.assertEqual(len(self.calls), 0)

    def test_unsupported_format_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            self._model(self._handler, output_format="ply")

    def test_text_to_3d_runs_preview_then_refine(self):
        model = self._model(self._handler)
        model.infer(prompt="a cat")

        posts = [call for call in self.calls if call.method == "POST"]
        self.assertTrue(posts[0].url.path.endswith("/openapi/v2/text-to-3d"))
        bodies = [json.loads(call.content) for call in posts]
        self.assertEqual(bodies[0]["mode"], "preview")
        self.assertEqual(bodies[1]["mode"], "refine")
        self.assertEqual(bodies[1]["preview_task_id"], "ms-1")
        self.assertEqual(len(model.last_call_info["task_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
