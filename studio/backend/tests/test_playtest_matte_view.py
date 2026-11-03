"""试玩舞台白底透明化 + 动作视角选择回归（离线）。

固化的契约：

1. cutout_white_background：白底/浅灰渐变底彩色主体 → 四角透明、主体
   不透明；已有透明区域原样返回；彩色复杂背景返回 None；下半身封闭白洞被回收；
2. collect_ai_strips(view_by_action=)：设置了期望视角的动作只接受
   meta.view 完全匹配的记录；正面记录再新也不能顶替 side；同动作同视角
   仍取 created_at 最新；未设置视角的 attack 保持旧行为。

全部为合成图 / 临时 JSON，不访问网络。

运行：``python -m unittest studio.backend.tests.test_playtest_matte_view -v``
"""

import json
import os
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
for path in (REPO_ROOT, BACKEND_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from artgen.sourceanim import cutout_white_background  # noqa: E402
from studio.backend.animation_service.service import collect_ai_strips  # noqa: E402
from studio.backend.api.routes import _side_source_facing  # noqa: E402
from studio.backend.model_service.service import TURNAROUND_SHEET_PROMPT  # noqa: E402

PLAYTEST_VIEW_BY_ACTION = {
    "idle": "front",
    "walk": "side",
    "run": "side",
    "jump": "side",
}


def _white_canvas(size=128) -> Image.Image:
    return Image.new("RGB", (size, size), (255, 255, 255))


def _alpha_corners(rgba: Image.Image, patch: int = 4) -> list[int]:
    alpha = rgba.convert("RGBA").getchannel("A")
    width, height = alpha.size
    boxes = [(0, 0), (width - patch, 0), (0, height - patch), (width - patch, height - patch)]
    return [alpha.crop((x, y, x + patch, y + patch)).getextrema()[1] for x, y in boxes]


class CutoutWhiteBackgroundTests(unittest.TestCase):
    def test_white_background_colored_subject_becomes_transparent(self):
        image = _white_canvas()
        ImageDraw.Draw(image).ellipse((34, 20, 94, 110), fill=(200, 40, 50))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.mode, "RGBA")
        self.assertLessEqual(max(_alpha_corners(result)), 8)
        self.assertEqual(result.getchannel("A").getpixel((64, 64)), 255)

    def test_already_transparent_image_is_returned_unchanged(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((16, 16, 48, 48), fill=(30, 140, 90, 255))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.convert("RGBA").tobytes(), image.tobytes())

    def test_non_white_background_returns_none(self):
        image = Image.new("RGB", (128, 128), (40, 80, 150))
        ImageDraw.Draw(image).ellipse((34, 20, 94, 110), fill=(255, 210, 60))
        self.assertIsNone(cutout_white_background(image))

    def test_neutral_gradient_background_is_matted(self):
        # i2v 模型会稳定地把白底源图生成为带暗角的浅灰渐变底；动作已成功
        # 落盘时不能因为“不是纯白”就把整条动画丢弃。
        image = Image.new("RGB", (128, 128))
        draw = ImageDraw.Draw(image)
        for y in range(128):
            value = 150 + round(y * 45 / 127)
            draw.line((0, y, 127, y), fill=(value, value, value))
        draw.ellipse((34, 20, 94, 110), fill=(35, 40, 45))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.getchannel("A").getpixel((64, 64)), 255)
        self.assertLessEqual(max(_alpha_corners(result)), 8)

    def test_letterboxed_white_video_content_is_matted(self):
        # AI 视频经 _fit 后常见：透明左右边栏 + 不透明白底内容矩形。
        # 不能因为已有透明像素就跳过内容区白底。
        image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        image.paste(Image.new("RGBA", (64, 128), (255, 255, 255, 255)), (32, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((45, 18, 83, 116), fill=(190, 50, 60, 255))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.getchannel("A").getpixel((64, 64)), 255)
        self.assertLessEqual(result.getchannel("A").getpixel((34, 64)), 8)
        self.assertLessEqual(result.getchannel("A").getpixel((94, 64)), 8)

    def test_letterboxed_white_content_with_subject_touching_border_is_matted(self):
        # 跳跃/大动作帧里角色可能贴到视频内容框边缘，使边缘近白比例下降；
        # 不能因此把整帧当作“已有透明素材”原样返回。
        image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        image.paste(Image.new("RGBA", (64, 128), (255, 255, 255, 255)), (32, 0))
        ImageDraw.Draw(image).ellipse((28, 12, 82, 124), fill=(190, 50, 60, 255))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.getchannel("A").getpixel((50, 64)), 255)
        self.assertLessEqual(result.getchannel("A").getpixel((92, 64)), 8)

    def test_enclosed_white_hole_in_lower_body_is_absorbed(self):
        # 下半身白色环形（两腿之间/脚边的封闭白洞）必须被回收为透明
        image = _white_canvas()
        draw = ImageDraw.Draw(image)
        draw.rectangle((34, 60, 94, 124), fill=(190, 50, 60))
        draw.rectangle((46, 80, 82, 116), fill=(255, 255, 255))
        result = cutout_white_background(image)
        self.assertIsNotNone(result)
        self.assertEqual(result.getchannel("A").getpixel((64, 98)), 0)
        self.assertEqual(result.getchannel("A").getpixel((40, 70)), 255)


def _write_meta(directory: str, animation_id: str, **fields) -> None:
    meta = {"id": animation_id, "frame_urls": [], "created_at": 0}
    meta.update(fields)
    with open(os.path.join(directory, f"{animation_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False)


def _touch_frames(directory: str, animation_id: str, count: int) -> list[str]:
    urls = []
    for index in range(count):
        name = f"{animation_id}_f{index}.png"
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(b"png")
        urls.append(f"/api/animation/{name}")
    return urls


class SideFacingContractTests(unittest.TestCase):
    def test_new_side_view_is_right_facing(self):
        asset = {"design_views": {"side": {"view": "side", "facing": "right"}}}
        self.assertEqual(_side_source_facing(asset), "right")
        self.assertIn("面朝画面右侧", TURNAROUND_SHEET_PROMPT)
        self.assertIn("朝右", TURNAROUND_SHEET_PROMPT)
        self.assertNotIn("面朝画面左侧", TURNAROUND_SHEET_PROMPT)

    def test_legacy_side_view_defaults_to_left(self):
        asset = {
            "design_views": {
                "side": {"view": "side", "source": "qwen-turnaround-sheet"}
            }
        }
        self.assertEqual(_side_source_facing(asset), "left")


class CollectAiStripsViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dir = self.directory.name
        self.asset = "ast10001"
        self.actions = ["idle", "walk", "run", "jump", "attack"]

    def test_expected_side_prefers_side_over_newer_front(self):
        _write_meta(self.dir, "front00", asset_id=self.asset, requested_action="walk",
                    view="front", created_at=300,
                    frame_urls=_touch_frames(self.dir, "front00", 5))
        _write_meta(self.dir, "side000", asset_id=self.asset, requested_action="walk",
                    view="side", created_at=100,
                    frame_urls=_touch_frames(self.dir, "side000", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions,
                                   view_by_action=PLAYTEST_VIEW_BY_ACTION)
        self.assertEqual(strips["walk"]["id"], "side000")

    def test_front_only_walk_is_not_used_as_side(self):
        _write_meta(self.dir, "front00", asset_id=self.asset, requested_action="walk",
                    view="front", created_at=500,
                    frame_urls=_touch_frames(self.dir, "front00", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions,
                                   view_by_action=PLAYTEST_VIEW_BY_ACTION)
        self.assertEqual(strips, {})

    def test_same_action_and_view_still_picks_latest(self):
        _write_meta(self.dir, "side001", asset_id=self.asset, requested_action="walk",
                    view="side", created_at=100,
                    frame_urls=_touch_frames(self.dir, "side001", 5))
        _write_meta(self.dir, "side002", asset_id=self.asset, requested_action="walk",
                    view="side", created_at=200,
                    frame_urls=_touch_frames(self.dir, "side002", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions,
                                   view_by_action=PLAYTEST_VIEW_BY_ACTION)
        self.assertEqual(strips["walk"]["id"], "side002")

    def test_idle_selects_front(self):
        _write_meta(self.dir, "idle000", asset_id=self.asset, requested_action="idle",
                    view="front", created_at=100,
                    frame_urls=_touch_frames(self.dir, "idle000", 5))
        _write_meta(self.dir, "idle001", asset_id=self.asset, requested_action="idle",
                    view="side", created_at=300,
                    frame_urls=_touch_frames(self.dir, "idle001", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions,
                                   view_by_action=PLAYTEST_VIEW_BY_ACTION)
        self.assertEqual(strips["idle"]["id"], "idle000")

    def test_attack_keeps_legacy_latest_behaviour(self):
        # attack 不在视角策略表内：不按视角过滤，仍取最新
        _write_meta(self.dir, "atk0001", asset_id=self.asset, requested_action="attack",
                    view="front", created_at=100,
                    frame_urls=_touch_frames(self.dir, "atk0001", 5))
        _write_meta(self.dir, "atk0002", asset_id=self.asset, requested_action="attack",
                    view="side", created_at=200,
                    frame_urls=_touch_frames(self.dir, "atk0002", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions,
                                   view_by_action=PLAYTEST_VIEW_BY_ACTION)
        self.assertEqual(strips["attack"]["id"], "atk0002")

    def test_without_view_map_behaviour_is_unchanged(self):
        _write_meta(self.dir, "front00", asset_id=self.asset, requested_action="walk",
                    view="front", created_at=300,
                    frame_urls=_touch_frames(self.dir, "front00", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions)
        self.assertEqual(strips["walk"]["id"], "front00")


if __name__ == "__main__":
    unittest.main()
