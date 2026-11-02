"""三视图手动生成回归（离线）：front 即角色原画，side / back 来自一次双栏生成。

固化的契约：

1. 三视图流程不做正面视角识别，不调用任何 VLM / qwen-vl-plus；
2. front 严格等于资产原画（file / url / model）；
3. 以原画为参考，一次调用 qwen-image-2.1-turbo 生成 side + back 双栏图；
4. qwen 是三视图唯一模型：失败直接抛真实错误，绝不回退 wanx2.1-imageedit；
5. 双栏图按白色间隔（兜底 50%）裁成 side / back 两个独立本地文件；
6. side / back 任一与 front 或彼此近乎重复、空白、尺寸过小即整体失败；
7. 失败时保留旧 design_views，不写入本次结果；
8. 角色生成阶段不自动生成三视图；角色重新生成后旧 design_views 被清除。

全部走 mock，不访问网络与真实模型。
运行：``python -m unittest studio.backend.tests.test_design_views -v``
"""

import os
import tempfile
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from studio.backend.model_service import service as svc

SOURCE_FILE = "source.png"
SOURCE_URL = "http://source/src.png"
SHEET_FILE = "sheet.png"
TURNAROUND_MODEL = "qwen-image-2.1-turbo"
MISSING_ART = "该资产没有可用的 AI 原画"


def _draw_front(path):
    """正面原画：竖椭圆（与 side / back 的条形轮廓明显不同）。"""

    image = Image.new("L", (256, 512), 255)
    ImageDraw.Draw(image).ellipse((58, 70, 198, 440), fill=0)
    image.save(path)


def _draw_bar_front(path):
    """条形原画：与「左栏复刻原画」的双栏图几乎一致，用于重复检测。"""

    image = Image.new("L", (256, 256), 255)
    ImageDraw.Draw(image).rectangle((90, 30, 150, 220), fill=0)
    image.save(path)


def _write_sheet(path, left_box, right_box):
    """双栏设定图：512×256，中间留有白色间隔，左右栏用给定色块区分。"""

    image = Image.new("L", (512, 256), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle(left_box, fill=0)
    draw.rectangle(right_box, fill=0)
    image.save(path)


def _write_distinct_sheet(path):
    # 左栏竖条（side）、右栏横条（back），互不相似，也不像竖椭圆原画
    _write_sheet(path, (90, 30, 150, 220), (316, 180, 456, 230))


def _write_side_duplicates_front_sheet(path):
    # 左栏与原画同构；右栏仍是横条
    _write_sheet(path, (90, 30, 150, 220), (316, 180, 456, 230))


def _write_views_duplicate_sheet(path):
    # 两栏同构 → side / back 彼此近乎重复
    _write_sheet(path, (90, 30, 150, 220), (340, 30, 400, 220))


class _Editor:
    """记录每次 edit 的参数，并返回给定的双栏结果。"""

    def __init__(self, result=None, error=None):
        self.result = result or {
            "file": SHEET_FILE,
            "url": "http://sheet/sheet.png",
            "model": TURNAROUND_MODEL,
        }
        self.error = error
        self.calls = []

    def edit(self, base_image_url, instruction, poll_timeout=180.0, allow_wanx_fallback=True):
        self.calls.append(
            {
                "url": base_image_url,
                "instruction": instruction,
                "allow_wanx_fallback": allow_wanx_fallback,
            }
        )
        if self.error:
            raise self.error
        return dict(self.result)


class TurnaroundServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.source_path = os.path.join(self.tmp, SOURCE_FILE)
        self.sheet_path = os.path.join(self.tmp, SHEET_FILE)
        _draw_front(self.source_path)
        _write_distinct_sheet(self.sheet_path)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, editor, sheet_prompt=None):
        vision = mock.Mock(side_effect=AssertionError("vision model must not be called"))
        with mock.patch.object(svc, "ImageEditProvider", return_value=editor), \
                mock.patch.object(svc, "VisionChatProvider", vision), \
                mock.patch.object(svc, "GENERATED_DIR", self.tmp):
            result = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen"},
                sheet_prompt=sheet_prompt,
            )
        vision.assert_not_called()
        return result

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

    def test_single_qwen_call_crops_two_distinct_files(self):
        editor = _Editor()
        views, failures = self._run(editor)
        # 只调用一次 qwen，且明确禁用 Wanx 兜底
        self.assertEqual(len(editor.calls), 1)
        self.assertEqual(editor.calls[0]["url"], SOURCE_URL)
        self.assertFalse(editor.calls[0]["allow_wanx_fallback"])
        self.assertIn("双栏", editor.calls[0]["instruction"])

        self.assertEqual(
            views["front"],
            {"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen", "view": "front"},
        )
        side, back = views["side"], views["back"]
        self.assertNotEqual(side["file"], back["file"])
        for view in (side, back):
            path = os.path.join(self.tmp, view["file"])
            self.assertTrue(os.path.isfile(path))
            with Image.open(path) as image:
                self.assertGreaterEqual(image.size[0], svc.TURNAROUND_VIEW_MIN_SIDE)
                self.assertGreaterEqual(image.size[1], svc.TURNAROUND_VIEW_MIN_SIDE)
        self.assertEqual(side["source"], "qwen-turnaround-sheet")
        self.assertEqual(side["sheet_file"], SHEET_FILE)
        self.assertEqual(side["model"], TURNAROUND_MODEL)
        self.assertEqual(back["model"], TURNAROUND_MODEL)
        self.assertEqual(side["view"], "side")
        self.assertEqual(back["view"], "back")
        self.assertEqual(len(side["bbox"]), 4)
        self.assertEqual(len(back["bbox"]), 4)
        self.assertEqual(side["bbox"][2], back["bbox"][0])  # 共用同一条裁切线
        self.assertEqual(failures, [])

    def test_custom_sheet_prompt_is_forwarded_to_editor(self):
        editor = _Editor()
        self._run(editor, sheet_prompt=svc.PVE_TURNAROUND_SHEET_PROMPT)
        self.assertEqual(editor.calls[0]["instruction"], svc.PVE_TURNAROUND_SHEET_PROMPT)
        # PVE 生物提示词不得沿用角色的单眼 / 双腿等人形假设
        self.assertNotIn("单眼", svc.PVE_TURNAROUND_SHEET_PROMPT)
        self.assertNotIn("双腿", svc.PVE_TURNAROUND_SHEET_PROMPT)

    def test_qwen_failure_propagates_real_error(self):
        editor = _Editor(error=RuntimeError(TURNAROUND_MODEL + " 调用失败：boom"))
        with self.assertRaises(RuntimeError) as caught:
            self._run(editor)
        self.assertIn(TURNAROUND_MODEL, str(caught.exception))
        self.assertIn("boom", str(caught.exception))

    def test_side_duplicating_front_fails(self):
        _draw_bar_front(self.source_path)
        self.sheet_path = os.path.join(self.tmp, SHEET_FILE)
        _write_side_duplicates_front_sheet(self.sheet_path)
        editor = _Editor()
        with self.assertRaises(svc.TurnaroundError) as caught:
            self._run(editor)
        message = str(caught.exception)
        self.assertIn("side", message)
        self.assertIn("原画", message)
        # 失败不留错误结果
        leftovers = [n for n in os.listdir(self.tmp) if n.startswith("turnaround_")]
        self.assertEqual(leftovers, [])

    def test_side_and_back_duplicate_each_other_fails(self):
        _write_views_duplicate_sheet(self.sheet_path)
        editor = _Editor()
        with self.assertRaises(svc.TurnaroundError) as caught:
            self._run(editor)
        message = str(caught.exception)
        self.assertIn("back", message)
        self.assertIn("侧面", message)

    def test_near_identical_uses_pixel_and_dhash(self):
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

    def test_turnaround_forces_turbo_edit_model(self):
        seen = {}

        def factory(settings):
            seen.update(settings)
            return _Editor()

        with mock.patch.object(svc, "ImageEditProvider", side_effect=factory), \
                mock.patch.object(svc, "GENERATED_DIR", self.tmp):
            svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": SOURCE_FILE, "url": SOURCE_URL, "model": "gen"},
            )
        self.assertEqual(seen["edit_model"], TURNAROUND_MODEL)

    def test_other_edit_chains_keep_default_model(self):
        # 只在三视图里指定 turbo；风格迁移/抠图/发层仍走原有默认模型
        self.assertEqual(svc.ImageEditProvider.QWEN_EDIT_MODEL, "qwen-image-edit")


class ImageEditProviderFallbackTests(unittest.TestCase):
    def test_disabled_fallback_never_calls_wanx(self):
        settings = {"api_key": "k", "edit_model": TURNAROUND_MODEL}
        provider = svc.ImageEditProvider(settings)
        with mock.patch.object(
            svc.ImageEditProvider, "_edit_qwen", side_effect=RuntimeError("boom")
        ), mock.patch.object(svc.ImageEditProvider, "_edit_wanx") as wanx:
            with self.assertRaises(RuntimeError) as caught:
                provider.edit(SOURCE_URL, "prompt", allow_wanx_fallback=False)
        wanx.assert_not_called()
        message = str(caught.exception)
        self.assertIn(TURNAROUND_MODEL, message)
        self.assertIn("boom", message)

    def test_default_fallback_still_uses_wanx(self):
        settings = {"api_key": "k"}
        provider = svc.ImageEditProvider(settings)
        with mock.patch.object(
            svc.ImageEditProvider, "_edit_qwen", side_effect=RuntimeError("boom")
        ), mock.patch.object(
            svc.ImageEditProvider,
            "_edit_wanx",
            return_value={"file": "edit.png", "url": "http://x", "model": "wanx2.1-imageedit"},
        ) as wanx, mock.patch(
            "studio.backend.model_service.usage.record_usage"
        ):
            result = provider.edit(SOURCE_URL, "prompt")
        wanx.assert_called_once()
        self.assertEqual(result["model"], "wanx2.1-imageedit")


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


def _asset(image=None, design_views=None):
    asset = {
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
    if design_views is not None:
        asset["design_views"] = design_views
    return asset


def _full_views():
    return {
        "front": {"file": "source.png", "url": "/api/generated/source.png", "view": "front"},
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
            return _full_views(), []

        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(svc, "generate_turnaround", side_effect=fake_generate):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["model"], TURNAROUND_MODEL)
        self.assertEqual(body["failures"], [])
        views = body["design_views"]
        self.assertEqual(views["front"]["file"], asset["image"]["file"])
        self.assertEqual(views["front"]["url"], asset["image"]["url"])
        self.assertEqual(views["front"]["view"], "front")
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

    def test_qwen_failure_returns_real_error_and_keeps_old_views(self):
        old_views = {
            "front": {"file": "old_front.png", "url": "/api/generated/old_front.png"},
            "side": {"file": "old_side.png", "url": "/api/generated/old_side.png"},
            "back": {"file": "old_back.png", "url": "/api/generated/old_back.png"},
        }
        asset = _asset(design_views=dict(old_views))
        app, runtime = self._app(asset)
        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(
                    svc,
                    "generate_turnaround",
                    side_effect=RuntimeError(TURNAROUND_MODEL + " 调用失败：quota exhausted"),
                ):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 502)
        detail = response.json()["detail"]
        self.assertIn(TURNAROUND_MODEL, detail)
        self.assertIn("quota exhausted", detail)
        runtime.assets.save.assert_not_called()
        self.assertEqual(runtime.assets.get.return_value["design_views"], old_views)

    def test_incomplete_views_do_not_overwrite_old(self):
        old_views = {"side": {"file": "old_side.png", "url": "/api/generated/old_side.png"}}
        asset = _asset(design_views=dict(old_views))
        app, runtime = self._app(asset)
        views = {"front": _full_views()["front"], "side": _full_views()["side"]}
        with mock.patch.object(svc, "safe_generated_path", return_value=self.local_file), \
                mock.patch.object(svc, "generate_turnaround", return_value=(views, [])):
            response = TestClient(app).post("/api/design/views", json={"asset_id": "a1"})
        self.assertEqual(response.status_code, 502)
        runtime.assets.save.assert_not_called()
        self.assertEqual(runtime.assets.get.return_value["design_views"], old_views)

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
