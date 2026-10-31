"""人物正面图驱动角色生成回归（离线）。

固化的契约：

1. 上传的正面图以真实图片格式校验，落盘为 ``reference_`` 前缀文件并返回可复用 meta；
2. ``POST /api/tasks`` 携带参考图文件名时，任务参数得到完整 meta（file/url/mime/尺寸/字节）；
3. 参考图分支把照片 URL 与身份锁定提示词传给生图服务，不会静默退回纯文本；
4. 参考图驱动的角色生成阶段直接产出三视图，失败只记录原因、保留原画与照片；
5. 未上传参考图时保持原流程，不调用三视图模型；
6. 非法格式 / 超限 / 非法任务参数被拒绝，且不留下半成品文件；
7. 参考图删除有引用保护；历史记录删除 / 清空后孤儿照片被清理；
8. 历史持久化后，重启后的新 Runtime 仍能通过 ``GET /api/assets/latest`` 读到参考图与三视图。

全部走 mock，不访问网络与真实模型，不读写真实 GENERATED_DIR / history.json。
运行：``python -m unittest studio.backend.tests.test_character_reference -v``
"""

import io
import os
import random
import tempfile
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from studio.backend.agent_runtime.runtime import AgentRuntime
from studio.backend.api import routes as routes_module
from studio.backend.history_service.service import HistoryStore
from studio.backend.model_service import service as svc

TURNAROUND_MODEL = "qwen-image-2.1-turbo"
IDENTITY_LOCK = "严格以参考图人物为唯一身份来源"
FULL_SETTINGS = {
    "enabled": True,
    "base_url": "http://x",
    "api_key": "k",
    "use_image": True,
    "model": "img-model",
}


def _png_bytes(width=320, height=640, offset=0):
    """白底 + 黑色竖椭圆，真实 PNG 内容。"""

    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).ellipse(
        (width // 2 - 50 + offset, 100, width // 2 + 50 + offset, height - 100),
        fill="black",
    )
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _gif_bytes(width=320, height=640):
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).ellipse(
        (width // 2 - 50, 100, width // 2 + 50, height - 100), fill="black"
    )
    buffer = io.BytesIO()
    image.save(buffer, "GIF")
    return buffer.getvalue()


def _noisy_png_bytes(width=320, height=640):
    """噪声 PNG：体积必然远超 1KB，用于模拟超限上传。"""

    generator = random.Random(7)
    raw = bytes(generator.randrange(256) for _ in range(width * height))
    image = Image.frombytes("L", (width, height), raw)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class _Supervisor:
    """最小主管线替身：直接返回给定资产，不跑真实管线。"""

    def __init__(self, asset=None):
        self.asset = asset

    def run(self, goal, asset=None, on_event=None, overrides=None):
        return {
            "asset": self.asset or asset,
            "supervisor": {"status": "success", "qa_rounds": 0},
        }


class _Settings:
    def __init__(self, effective=None):
        self._effective = effective or {"enabled": False}

    def effective(self):
        return self._effective


def _client(runtime):
    app = FastAPI()
    app.include_router(routes_module.build_router(runtime))
    return TestClient(app)


class _TempGeneratedDir(unittest.TestCase):
    """把 GENERATED_DIR 指向每个用例独立的临时目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self._dir_patch = mock.patch.object(svc, "GENERATED_DIR", self.tmp)
        self._dir_patch.start()

    def tearDown(self):
        self._dir_patch.stop()
        self._tmp.cleanup()

    def _write_file(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def _reference_meta(self, name="reference_front.png", data=None):
        data = data if data is not None else _png_bytes()
        self._write_file(name, data)
        info = svc.validate_reference_image(data)
        return {
            "file": name,
            "url": "/api/generated/" + name,
            "mime": info["mime"],
            "width": info["width"],
            "height": info["height"],
            "bytes": info["bytes"],
        }

    def _reference_files(self):
        return [name for name in os.listdir(self.tmp) if name.startswith("reference_")]


class ReferenceUploadRouteTests(_TempGeneratedDir):
    def _fake_runtime(self):
        runtime = mock.Mock()
        runtime.start_task.return_value = "T0001"
        runtime.model_settings.effective.return_value = {"enabled": True, "api_key": "k"}
        return runtime

    def test_upload_reference_returns_real_file_meta(self):
        client = _client(self._fake_runtime())
        response = client.post(
            "/api/character/reference",
            files={"file": ("front.png", _png_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["file"].startswith("reference_"))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, body["file"])))
        self.assertEqual(body["mime"], "image/png")
        self.assertEqual(body["width"], 320)
        self.assertEqual(body["height"], 640)
        self.assertEqual(body["url"], "/api/generated/" + body["file"])
        self.assertEqual(body["bytes"], len(_png_bytes()))

    def test_task_accepts_uploaded_reference_meta(self):
        runtime = self._fake_runtime()
        client = _client(runtime)
        uploaded = client.post(
            "/api/character/reference",
            files={"file": ("front.png", _png_bytes(), "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200)
        uploaded_meta = uploaded.json()

        response = client.post(
            "/api/tasks",
            json={"goal": "创角", "reference_image": uploaded_meta["file"]},
        )
        self.assertEqual(response.status_code, 202)
        runtime.start_task.assert_called_once()
        meta = runtime.start_task.call_args.kwargs["reference_image"]
        for key in ("file", "url", "mime", "width", "height", "bytes"):
            self.assertIn(key, meta)
        self.assertEqual(meta["file"], uploaded_meta["file"])
        self.assertEqual(meta["url"], "/api/generated/" + uploaded_meta["file"])
        self.assertEqual(meta["mime"], "image/png")
        self.assertEqual(meta["width"], 320)
        self.assertEqual(meta["height"], 640)
        self.assertEqual(meta["bytes"], uploaded_meta["bytes"])


class InvalidReferenceTests(_TempGeneratedDir):
    def _fake_runtime(self):
        runtime = mock.Mock()
        runtime.start_task.return_value = "T0001"
        runtime.model_settings.effective.return_value = {"enabled": True, "api_key": "k"}
        return runtime

    def test_gif_content_is_rejected_by_real_format(self):
        client = _client(self._fake_runtime())
        response = client.post(
            "/api/character/reference",
            files={"file": ("front.png", _gif_bytes(), "image/gif")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("JPG / PNG / WebP", response.json()["detail"])
        self.assertEqual(self._reference_files(), [])

    def test_oversized_upload_is_rejected(self):
        client = _client(self._fake_runtime())
        with mock.patch.object(svc, "MAX_REFERENCE_BYTES", 1024):
            response = client.post(
                "/api/character/reference",
                files={"file": ("front.png", _noisy_png_bytes(), "image/png")},
            )
        self.assertEqual(response.status_code, 413)
        self.assertIn("10MB", response.json()["detail"])
        self.assertEqual(self._reference_files(), [])

    def test_task_rejects_missing_or_non_reference_file(self):
        runtime = self._fake_runtime()
        client = _client(runtime)

        missing = client.post(
            "/api/tasks",
            json={"goal": "创角", "reference_image": "reference_missing.png"},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("重新上传", missing.json()["detail"])

        self._write_file("art.png", _png_bytes())
        plain = client.post(
            "/api/tasks",
            json={"goal": "创角", "reference_image": "art.png"},
        )
        self.assertEqual(plain.status_code, 400)
        self.assertIn("重新上传", plain.json()["detail"])
        runtime.start_task.assert_not_called()


class ReferenceRuntimeTests(_TempGeneratedDir):
    def setUp(self):
        super().setUp()
        self.history_path = os.path.join(self.tmp, "history.json")

    def _runtime(self, settings=None, supervisor_asset=None):
        return AgentRuntime(
            supervisor=_Supervisor(supervisor_asset or {"id": "a1", "name": "新角色"}),
            history=HistoryStore(self.history_path),
            model_settings=_Settings(settings or {"enabled": True}),
        )

    def _image(self):
        self._write_file("art.png", _png_bytes())
        return {
            "file": "art.png",
            "url": "/api/generated/art.png",
            "model": TURNAROUND_MODEL,
            "provider": "dashscope",
        }

    @staticmethod
    def _views():
        return {
            "front": {"file": "art.png", "url": "/api/generated/art.png", "view": "front"},
            "side": {
                "file": "side.png",
                "url": "/api/generated/side.png",
                "model": TURNAROUND_MODEL,
                "view": "side",
            },
            "back": {
                "file": "back.png",
                "url": "/api/generated/back.png",
                "model": TURNAROUND_MODEL,
                "view": "back",
            },
        }

    def test_reference_run_saves_views_and_history_reload(self):
        ref_meta = self._reference_meta()
        runtime = self._runtime()
        image = self._image()
        views = self._views()
        task_id = runtime.tasks.create("打造角色")
        with mock.patch.object(
            AgentRuntime, "_call_external", return_value=(None, image, None)
        ), mock.patch.object(
            svc, "generate_turnaround", return_value=(views, [])
        ) as turnaround:
            runtime._run(task_id, "打造角色", reference_image=ref_meta)

        saved = runtime.assets.get("a1")
        self.assertEqual(saved["reference_image"], ref_meta)
        self.assertEqual(saved["design_views"], views)
        self.assertNotIn("design_views_error", saved)
        self.assertEqual(turnaround.call_args.kwargs["front_image"], image)

        task = runtime.tasks.get(task_id)
        self.assertEqual(task["status"], "success")
        self.assertIn("MODEL_VIEWS", [event["type"] for event in task["events"]])

        # 复用同一个 HistoryStore 路径的新 Runtime：内存资产为空，但历史可重读
        reloaded = self._runtime()
        self.assertIsNone(reloaded.assets.latest())
        client = _client(reloaded)
        response = client.get("/api/assets/latest")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reference_image"]["file"], ref_meta["file"])
        self.assertIn("design_views", body)
        for view in ("side", "back"):
            meta = body["design_views"][view]
            self.assertEqual(meta["url"], "/api/generated/" + meta["file"])

    def test_without_reference_keeps_original_flow(self):
        runtime = self._runtime()
        image = self._image()
        task_id = runtime.tasks.create("创角")
        with mock.patch.object(
            AgentRuntime, "_call_external", return_value=(None, image, None)
        ), mock.patch.object(svc, "generate_turnaround") as turnaround:
            runtime._run(task_id, "创角")

        turnaround.assert_not_called()
        saved = runtime.assets.latest()
        self.assertIsNotNone(saved)
        self.assertNotIn("reference_image", saved)
        self.assertNotIn("design_views", saved)

    def test_reference_branch_passes_photo_and_identity_prompt(self):
        runtime = self._runtime(settings=dict(FULL_SETTINGS))
        task_id = runtime.tasks.create("打造一个银发战士")
        ref_meta = self._reference_meta()
        image = {
            "file": "art.png",
            "url": "/api/generated/art.png",
            "model": TURNAROUND_MODEL,
            "provider": "dashscope",
        }
        with mock.patch.object(
            svc, "generate_from_reference", return_value=image
        ) as generate:
            _enhanced, result, error = runtime._call_external(
                task_id,
                "打造一个银发战士",
                {},
                {"style": "2d"},
                reference_image=ref_meta,
            )

        self.assertEqual(generate.call_args.args[1], ref_meta["url"])
        prompt = generate.call_args.args[2]
        self.assertIn(IDENTITY_LOCK, prompt)
        self.assertIn("银发战士", prompt)
        self.assertIsNotNone(result)
        self.assertIsNone(error)

    def test_turnaround_failure_keeps_photo_and_can_retry(self):
        ref_meta = self._reference_meta()
        runtime = self._runtime(settings=dict(FULL_SETTINGS))
        image = self._image()
        views = self._views()
        task_id = runtime.tasks.create("创角")
        with mock.patch.object(
            AgentRuntime, "_call_external", return_value=(None, image, None)
        ), mock.patch.object(
            svc,
            "generate_turnaround",
            side_effect=RuntimeError("qwen-image-2.1-turbo 调用失败：boom"),
        ):
            runtime._run(task_id, "创角", reference_image=ref_meta)

        task = runtime.tasks.get(task_id)
        self.assertEqual(task["status"], "success")
        saved = runtime.assets.get("a1")
        self.assertEqual(saved["reference_image"], ref_meta)
        self.assertNotIn("design_views", saved)
        self.assertIn("boom", saved["design_views_error"]["detail"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ref_meta["file"])))
        fallback = [
            event
            for event in task["events"]
            if event["type"] == "MODEL_FALLBACK" and event.get("stage") == "views"
        ]
        self.assertTrue(fallback)

        # 设计中心重试：同一资产补生成三视图，失败原因被清除
        routes_module._VIEW_LOCKS.clear()
        client = _client(runtime)
        with mock.patch.object(svc, "generate_turnaround", return_value=(views, [])):
            response = client.post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved["design_views"], views)
        # 路由先 pop 掉失败原因，随后 history.patch_asset 以 None 回填同一份
        # 资产快照——None 即「已清除」，前端按真值判断不会再展示错误。
        self.assertIsNone(saved.get("design_views_error"))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ref_meta["file"])))

    def test_reference_without_image_model_fails_and_keeps_photo(self):
        ref_meta = self._reference_meta()
        runtime = self._runtime(
            settings={"enabled": False, "image_fallback_policy": "degrade"}
        )
        task_id = runtime.tasks.create("创角")
        runtime._run(task_id, "创角", reference_image=ref_meta)

        task = runtime.tasks.get(task_id)
        self.assertEqual(task["status"], "failed")
        self.assertIn("图片模型未启用", task["error"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ref_meta["file"])))
        self.assertIsNone(runtime.assets.latest())


class ReferenceCleanupRouteTests(_TempGeneratedDir):
    def setUp(self):
        super().setUp()
        self.history_path = os.path.join(self.tmp, "history.json")
        self.runtime = AgentRuntime(
            supervisor=_Supervisor({"id": "a1", "name": "ref"}),
            history=HistoryStore(self.history_path),
            model_settings=_Settings({"enabled": True}),
        )
        self.client = _client(self.runtime)

    def test_referenced_photo_is_protected_then_history_cleanup(self):
        keep = svc.save_reference_image(_png_bytes(offset=0))
        orphan = svc.save_reference_image(_png_bytes(offset=30))
        keep_path = os.path.join(self.tmp, keep["file"])
        orphan_path = os.path.join(self.tmp, orphan["file"])

        self.runtime.assets.save(
            {"id": "a1", "name": "ref", "reference_image": keep}
        )
        self.runtime.history.add(
            {
                "id": "H1",
                "task_id": "T1",
                "asset": {"id": "hasset", "reference_image": orphan},
            }
        )

        protected = self.client.delete("/api/character/reference/" + keep["file"])
        self.assertEqual(protected.status_code, 409)
        self.assertIn("仍被角色引用", protected.json()["detail"])
        self.assertTrue(os.path.isfile(keep_path))

        # 仅被历史记录引用 → 仍受保护
        history_protected = self.client.delete(
            "/api/character/reference/" + orphan["file"]
        )
        self.assertEqual(history_protected.status_code, 409)
        self.assertTrue(os.path.isfile(orphan_path))

        # 未被任何记录引用的新上传图可以删除
        uploaded = self.client.post(
            "/api/character/reference",
            files={"file": ("front.png", _png_bytes(offset=60), "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200)
        new_file = uploaded.json()["file"]
        new_path = os.path.join(self.tmp, new_file)
        self.assertTrue(os.path.isfile(new_path))
        deleted = self.client.delete("/api/character/reference/" + new_file)
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(os.path.exists(new_path))

        # 删除历史记录后，只被它引用的 orphan 被清理
        response = self.client.delete("/api/history/H1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(orphan_path))
        self.assertTrue(os.path.isfile(keep_path))

    def test_clear_history_removes_only_referenced_orphans(self):
        keep = svc.save_reference_image(_png_bytes(offset=0))
        clear = svc.save_reference_image(_png_bytes(offset=30))
        keep_path = os.path.join(self.tmp, keep["file"])
        clear_path = os.path.join(self.tmp, clear["file"])

        self.runtime.assets.save(
            {"id": "a1", "name": "ref", "reference_image": keep}
        )
        self.runtime.history.add(
            {
                "id": "H2",
                "task_id": "T2",
                "asset": {"id": "hasset", "reference_image": clear},
            }
        )

        response = self.client.delete("/api/history")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(clear_path))
        self.assertTrue(os.path.isfile(keep_path))


if __name__ == "__main__":
    unittest.main()
