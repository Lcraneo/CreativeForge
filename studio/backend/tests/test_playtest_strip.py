"""试玩 AI 条带打包（playtest_strip）的缓存命名与抽样口径。"""

import os
import tempfile
import unittest

from PIL import Image, ImageDraw

from studio.backend.animation_service import playtest_strip


def _make_frame(path: str, shift: int) -> None:
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12 + shift, 8, 44 + shift, 56), fill=(40, 80, 160, 255))
    image.save(path, "PNG")


class PlaytestStripTests(unittest.TestCase):
    def test_sample_indexes_covers_loop(self):
        indexes = playtest_strip.sample_indexes(32)
        self.assertEqual(len(indexes), playtest_strip.MAX_FRAMES)
        self.assertEqual(indexes[0], 0)
        self.assertEqual(indexes[-1], 31)
        self.assertEqual(playtest_strip.sample_indexes(5), [0, 1, 2, 3, 4])

    def test_cache_names_prefer_sampled_version(self):
        meta = {
            "id": "anim123",
            "requested_action": "idle",
            "frame_urls": ["/api/animation/f{:02d}.png".format(index) for index in range(32)],
        }
        names = playtest_strip.cache_names(meta)
        self.assertEqual(len(names), 3)
        self.assertEqual(names[0][1], 16)
        self.assertIn("matte-v5", names[0][0])
        # 旧缓存按全量帧数命名：升级后仍可直接复用，避免重新抠图
        self.assertEqual(names[1][1], 32)
        self.assertIn("matte-v4", names[1][0])

    def test_build_and_reuse_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            frame_dir = os.path.join(temp, "frames")
            cache_dir = os.path.join(temp, "cache")
            os.makedirs(frame_dir)
            frame_urls = []
            for index in range(6):
                name = "frame_f{:02d}.png".format(index)
                _make_frame(os.path.join(frame_dir, name), index)
                frame_urls.append("/api/animation/" + name)
            meta = {
                "id": "anim456",
                "requested_action": "walk",
                "frame_urls": frame_urls,
            }
            built = playtest_strip.build_strip(meta, frame_dir, cache_dir)
            self.assertIsNotNone(built)
            path, frames = built
            self.assertTrue(os.path.isfile(path))
            self.assertEqual(frames, 6)
            cached = playtest_strip.cached_strip_path(cache_dir, meta)
            self.assertEqual(cached, (path, 6))
            # 再次打包直接命中缓存，不再抠图
            self.assertEqual(playtest_strip.build_strip(meta, frame_dir, cache_dir), built)


if __name__ == "__main__":
    unittest.main()
