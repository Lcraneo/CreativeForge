"""三视图手动生成回归（离线）：front 即角色原画，side / back 独立派生。

固化的契约：

1. 三视图流程不做正面视角识别，不调用任何 VLM / qwen-vl-plus；
2. front 严格等于资产原画（file / url / model）；
3. side / back 均以同一张原画为输入，互不依赖；
4. 原画缺失或不可读时返回 409（该资产没有可用的 AI 原画）；
5. side 成功、back 失败时保留 side（反之亦然），两侧都失败不写假数据；
6. 角色生成阶段不自动生成三视图；
7. 角色重新生成后旧 design_views 被清除；
8. 角色原画 prompt 追加完整全身构图约束并移除冲突视角词。

全部走 mock，不访问网络与真实模型。
运行：``python -m unittest studio.backend.tests.test_design_views -v``
"""

import os
import tempfile
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.model_service import service as svc

SOURCE_FILE = "source.png"
SOURCE_URL = "http://source/src.png"
SIDE_URL = "http://side/side.png"
BACK_URL = "http://back/back.png"
MISSING_ART = "该资产没有可用的 AI 原画"


def _side_result():
    return {"file": "side.png", "url": SIDE_URL, "model": "edit"}


def _back_result():
    return {"file": "back.png", "url": BACK_URL, "model": "edit"}


class _Editor:
    """记录每次 edit 的 (base_image_url, instruction)，并按下标返回结果。"""

    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []
        self._index = 0

    def edit(self, base_image_url, instruction, poll_timeout=180.0):
        self.calls.append((base_image_url, instruction))
        if self.error:
            raise RuntimeError(self.error)
        result = dict(self.results[min(self._index, len(self.results) - 1)])
        self._index += 1
        return result


class TurnaroundServiceTests(unittest.TestCase):
    def test_no_view_classifier_remains(self):
        # 正面识别链路（VLM / canonical front gate）必须整体移除
        for name in (
            "_classify_character_view",
            "normalize_front",
            "validate_front",
            "CanonicalFrontError",
            "FrontNotUsableError",
        ):
            self.assertFalse(hasattr(svc, name), name)

    def test_front_is_source_and_side_back_use_same_input(self):
        editor = _Editor([_side_result(), _back_result()])
        vision = mock.Mock(side_effect=AssertionError("vision model must not be called"))
        with mock.patch.object(svc, "ImageEditProvider", return_value=editor), \
                mock.patch.object(svc, "VisionChatProvider", vision), \
                mock.patch.object(svc, "_near_identical", return_value=(False, None)):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen"},
            )
        self.assertEqual(
            views["front"],
            {"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen", "view": "front"},
        )
        vision.assert_not_called()
        # side / back 都以同一张原画为输入，各一次独立请求
        self.assertEqual([call[0] for call in editor.calls], [SOURCE_URL, SOURCE_URL])
        self.assertNotIn("side", editor.calls[1][1])
        self.assertEqual(failures, [])

    def test_side_success_back_failure_keeps_side(self):
        editor = _Editor([_side_result()])

        def edit(base_image_url, instruction, poll_timeout=180.0):
            editor.calls.append((base_image_url, instruction))
            if "正后方" in instruction:
                raise RuntimeError("back failed")
            return _side_result()

        editor.edit = edit
        with mock.patch.object(svc, "ImageEditProvider", return_value=editor), \
                mock.patch.object(svc, "_near_identical", return_value=(False, None)):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen"},
            )
        self.assertEqual(views["side"]["url"], SIDE_URL)
        self.assertNotIn("back", views)
        self.assertEqual(len(failures), 1)
        self.assertIn("back", failures[0])

    def test_near_identical_uses_pixel_and_dhash(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, box in (
                ("source.png", (0, 0, 32, 64)),
                ("reused.png", (0, 0, 32, 64)),
                ("side.png", (32, 0, 64, 64)),
            ):
                image = Image.new("L", (64, 64), 255)
                ImageDraw.Draw(image).rectangle(box, fill=0)
                path = os.path.join(tmp, name)
                image.save(path)
                paths.append(path)
            reused, detail = svc._near_identical(paths[0], paths[1])
            self.assertTrue(reused)
            changed, _ = svc._near_identical(paths[0], paths[2])
            self.assertFalse(changed)
            self.assertIn("dHash", detail)

    def test_both_views_failed_returns_front_only(self):
        editor = _Editor(error="boom")
        with mock.patch.object(svc, "ImageEditProvider", return_value=editor):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen"},
            )
        self.assertEqual(list(views), ["front"])
        self.assertEqual(len(failures), 2)
        self.assertIn("side", failures[0])
        self.assertIn("back", failures[1])


class CharacterPromptTests(unittest.TestCase):
    def test_prompt_appends_full_body_framing_and_drops_conflicts(self):
        from agent.generation.external import build_image_prompt

        prompt = build_image_prompt(
            "一个精灵弓箭手，单人，侧视站立姿势，背面，回头看", None, None, style=None
        )
        for conflict in ("侧视站立", "背面", "回头看"):
            self.assertNotIn(conflict, prompt)
        self.assertIn("精灵弓箭手", prompt)
        self.assertIn("正面或轻微三分之四侧身", prompt)
        self.assertIn("双脚完整露出", prompt)
        self.assertIn("纯白背景", prompt)


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
    def effective(self):
        return {"enabled": False}


class RuntimeViewsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        from studio.backend.agent_runtime.runtime import AgentRuntime
        from studio.backend.history_service.service import HistoryStore

        self.history_path = os.path.join(self._tmp.name, "history.json")
        self.AgentRuntime = AgentRuntime
        self.HistoryStore = HistoryStore

    def tearDown(self):
        self._tmp.cleanup()

    def _runtime(self, asset=None):
        return self.AgentRuntime(
            supervisor=_Supervisor(asset or {"id": "a1", "name": "新角色"}),
            history=self.HistoryStore(self.history_path),
            model_settings=_Settings(),
        )

    def test_task_generation_never_calls_views_model(self):
        image = {
            "file": "source.png",
            "url": "/api/generated/source.png",
            "model": "gen",
            "provider": "dashscope",
        }
        runtime = self._runtime()
        task_id = runtime.tasks.create("创角")
        with mock.patch.object(
            self.AgentRuntime, "_call_external", return_value=(None, image, None)
        ), mock.patch.object(svc, "generate_turnaround") as turnaround:
            runtime._run(task_id, "创角")
        turnaround.assert_not_called()
        saved = runtime.assets.latest()
        self.assertIsNotNone(saved)
        self.assertNotIn("design_views", saved)

    def test_regenerated_asset_drops_old_design_views(self):
        asset = {
            "id": "a1",
            "name": "旧角色",
            "design_views": {
                "front": {"file": "old_front.png", "url": "/api/generated/old_front.png"},
                "side": {"file": "old_side.png", "url": "/api/generated/old_side.png"},
            },
        }
        runtime = self._runtime(asset)
        task_id = runtime.tasks.create("重新生成")
        with mock.patch.object(
            self.AgentRuntime, "_call_external", return_value=(None, None, None)
        ):
            runtime._run(task_id, "重新生成", asset=asset)
        saved = runtime.assets.get("a1")
        self.assertIsNotNone(saved)
        self.assertNotIn("design_views", saved)


def _asset(image=None):
    return {
        "id": "a1",
        "image": image
        if image is not None
        else {
            "file": "source.png",
            "url": "/api/generated/source.png",
            "model": "gen",
            "provider": "dashscope",
        },
    }


class DesignViewsRouteTests(unittest.TestCase):
    def setUp(self):
        from studio.backend.api import routes as routes_module

        self.routes = routes_module
        self.routes._VIEW_LOCKS.clear()
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.close()
        self.local_file = handle.name

    def tearDown(self):
        try:
            os.unlink(self.local_file)
        except OSError:
            pass

    def _app(self, asset=None):
        runtime = mock.Mock()
        runtime.assets.get.return_value = asset if asset is not None else _asset()
        runtime.assets.save.return_value = "a1"
        runtime.history.patch_asset.return_value = True
        runtime.model_settings.effective.return_value = {"enabled": True, "api_key": "k"}
        app = FastAPI()
        app.include_router(self.routes.build_router(runtime))
        return app, runtime

    def _post(self, app, asset_id="a1"):
        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file):
            return TestClient(app).post("/api/design/views", json={"asset_id": asset_id})

    def test_front_is_asset_image_and_side_back_use_it(self):
        asset = _asset()
        app, runtime = self._app(asset)
        captured = {}

        def fake_generate(settings, base_url, front_image=None, deadline=None, on_result=None):
            captured["front_image"] = dict(front_image)
            front = {
                "file": front_image.get("file"),
                "url": front_image.get("url"),
                "model": front_image.get("model"),
                "view": "front",
            }
            return (
                {
                    "front": front,
                    "side": {"file": "side.png", "url": "/api/generated/side.png", "view": "side"},
                    "back": {"file": "back.png", "url": "/api/generated/back.png", "view": "back"},
                },
                [],
            )

        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(svc, "generate_turnaround", side_effect=fake_generate):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["design_views"]
        self.assertEqual(body["front"]["file"], asset["image"]["file"])
        self.assertEqual(body["front"]["url"], asset["image"]["url"])
        self.assertEqual(body["front"]["view"], "front")
        # side / back 的输入都是 asset.image
        self.assertEqual(captured["front_image"], asset["image"])
        runtime.assets.save.assert_called_once()
        runtime.history.patch_asset.assert_called_once()

    def test_missing_asset_image_returns_409(self):
        app, runtime = self._app(_asset(image={}))
        response = self._post(app)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], MISSING_ART)
        runtime.assets.save.assert_not_called()

    def test_unreadable_asset_image_returns_409(self):
        app, runtime = self._app()
        with mock.patch.object(svc, "safe_generated_path", return_value=None):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], MISSING_ART)
        runtime.assets.save.assert_not_called()

    def test_partial_result_merges_with_previous_views(self):
        asset = _asset()
        asset["design_views"] = {
            "side": {"file": "old_side.png", "url": "/api/generated/old_side.png"}
        }
        app, runtime = self._app(asset)
        views = {
            "front": {
                "file": "source.png",
                "url": "/api/generated/source.png",
                "model": "gen",
                "view": "front",
            },
            "back": {"file": "back.png", "url": "/api/generated/back.png", "view": "back"},
        }
        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(
                    svc, "generate_turnaround", return_value=(views, ["side: 生成失败"])
                ):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()["design_views"]
        self.assertEqual(body["side"]["url"], "/api/generated/old_side.png")
        self.assertEqual(body["back"]["url"], "/api/generated/back.png")
        self.assertEqual(response.json()["failures"], ["side: 生成失败"])

    def test_both_views_failed_does_not_save_fake_views(self):
        views = {"front": {"file": "source.png", "url": "/api/generated/source.png"}}
        app, runtime = self._app()
        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(
                    svc, "generate_turnaround", return_value=(views, ["side: x", "back: y"])
                ):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("side: x", response.json()["detail"])
        self.assertIn("back: y", response.json()["detail"])
        runtime.assets.save.assert_not_called()
        self.assertNotIn("design_views", runtime.assets.get.return_value)

    def test_duplicate_request_blocked_while_generating(self):
        app, _runtime = self._app()
        lock = self.routes._view_lock("a1")
        lock.acquire()
        try:
            response = self._post(app)
        finally:
            lock.release()
        self.assertEqual(response.status_code, 409)
        self.assertIn("正在生成", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
