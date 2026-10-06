"""动作身份命名空间回归：自定义动作与内置动作严格隔离。

修复的缺陷：自定义动作生成时以基础动作词（如 walk）入账
meta.requested_action → 试玩舞台按动作名匹配时，自定义动画抢占内置
walk 条带、批次补齐错误跳过 walk。固化契约：

1. collect_ai_strips：内置槽位只收无前缀内置动作名，custom: 记录永不入选；
2. existing_ai_actions：自定义记录不算内置动作已交付；
3. action_matrix：自定义记录不占内置动作格；
4. CustomActionStore 与内置动作同名也互不污染（独立命名空间）。
"""

import json
import os
import tempfile
import unittest

from studio.backend.animation_service.custom_actions import CustomActionStore
from studio.backend.animation_service.service import (
    ACTIONS,
    AnimationService,
    collect_ai_strips,
    custom_action_identity,
    parse_action_identity,
    sanitize_custom_action,
)


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


class IdentityHelperTests(unittest.TestCase):
    def test_identity_roundtrip(self):
        self.assertEqual(parse_action_identity("walk"), ("base", "walk"))
        self.assertEqual(
            parse_action_identity(custom_action_identity("原地敲竹板待机循环动画")),
            ("custom", "原地敲竹板待机循环动画"),
        )
        self.assertEqual(parse_action_identity(None), ("base", ""))
        self.assertEqual(parse_action_identity(""), ("base", ""))

    def test_sanitize_strips_prefix_and_blank(self):
        self.assertEqual(sanitize_custom_action(" 敲竹板 "), "敲竹板")
        # 请求侧误带前缀时剥掉，避免 custom:custom: 叠加
        self.assertEqual(sanitize_custom_action("custom:敲竹板"), "敲竹板")
        self.assertIsNone(sanitize_custom_action(None))
        self.assertIsNone(sanitize_custom_action("   "))
        self.assertEqual(len(sanitize_custom_action("长" * 60) or ""), 40)


class CollectAiStripsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dir = self.directory.name
        self.asset = "ast10001"
        self.actions = list(ACTIONS)

    def test_builtin_action_matches_latest_genuine_animation(self):
        _write_meta(self.dir, "old000", asset_id=self.asset, requested_action="walk",
                    created_at=100, frame_urls=_touch_frames(self.dir, "old000", 5))
        _write_meta(self.dir, "new000", asset_id=self.asset, requested_action="walk",
                    created_at=200, frame_urls=_touch_frames(self.dir, "new000", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions)
        self.assertEqual(set(strips), {"walk"})
        self.assertEqual(strips["walk"]["id"], "new000")

    def test_custom_action_never_takes_builtin_slot(self):
        # 复现缺陷：自定义动作（运动族 walk）比内置 walk 更新——修复前
        # 它以 requested_action="walk" 入账并抢占条带；修复后 custom: 身份被拒
        _write_meta(self.dir, "genuine0", asset_id=self.asset, requested_action="walk",
                    created_at=100, frame_urls=_touch_frames(self.dir, "genuine0", 5))
        _write_meta(self.dir, "custom0", asset_id=self.asset,
                    requested_action=custom_action_identity("原地敲竹板待机循环动画"),
                    created_at=200, frame_urls=_touch_frames(self.dir, "custom0", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions)
        self.assertEqual(set(strips), {"walk"})
        self.assertEqual(strips["walk"]["id"], "genuine0")

    def test_same_name_custom_action_is_namespaced_not_colliding(self):
        # 同名冲突：自定义动作恰好叫 "walk" → custom:walk ≠ walk
        _write_meta(self.dir, "custom00", asset_id=self.asset,
                    requested_action=custom_action_identity("walk"),
                    created_at=300, frame_urls=_touch_frames(self.dir, "custom00", 5))
        strips = collect_ai_strips(self.dir, self.asset, self.actions)
        self.assertEqual(strips, {})

    def test_other_asset_and_sparse_frames_are_excluded(self):
        _write_meta(self.dir, "other000", asset_id="ast99999", requested_action="walk",
                    created_at=999, frame_urls=_touch_frames(self.dir, "other000", 5))
        _write_meta(self.dir, "sparse00", asset_id=self.asset, requested_action="walk",
                    created_at=150, frame_urls=_touch_frames(self.dir, "sparse00", 2))
        self.assertEqual(collect_ai_strips(self.dir, self.asset, self.actions), {})

    def test_no_asset_returns_empty(self):
        self.assertEqual(collect_ai_strips(self.dir, None, self.actions), {})


class ExistingAiActionsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = AnimationService(self.directory.name)
        self.asset = "ast10001"

    def test_custom_animation_does_not_mark_builtin_done(self):
        # 缺陷回归：自定义动作（运动族 walk）曾让批次补齐误判 walk 已交付
        _write_meta(self.service.directory, "custom00", source="video",
                    asset_id=self.asset,
                    requested_action=custom_action_identity("原地敲竹板待机循环动画"),
                    frame_urls=_touch_frames(self.service.directory, "custom00", 5))
        self.assertEqual(self.service.existing_ai_actions(self.asset), set())

    def test_builtin_animation_marks_done(self):
        _write_meta(self.service.directory, "genuine0", source="video",
                    asset_id=self.asset, requested_action="walk",
                    frame_urls=_touch_frames(self.service.directory, "genuine0", 5))
        self.assertEqual(self.service.existing_ai_actions(self.asset), {"walk"})


class ActionMatrixTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = AnimationService(self.directory.name)
        self.asset = "ast10001"

    def test_custom_records_excluded_from_builtin_matrix_cells(self):
        _write_meta(self.service.directory, "genuine0", asset_id=self.asset,
                    requested_action="walk", view="front",
                    frame_urls=_touch_frames(self.service.directory, "genuine0", 3))
        _write_meta(self.service.directory, "custom00", asset_id=self.asset,
                    requested_action=custom_action_identity("原地敲竹板待机循环动画"),
                    view="side",
                    frame_urls=_touch_frames(self.service.directory, "custom00", 3))
        matrix = self.service.action_matrix(self.asset)
        cell_keys = {(cell["action"], cell["view"]) for cell in matrix["cells"]}
        self.assertEqual(cell_keys, {("walk", "front")})


class CustomActionStoreNamespaceTests(unittest.TestCase):
    def test_custom_action_named_like_builtin_stays_independent(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = CustomActionStore(os.path.join(directory.name, "custom_actions.json"))
        saved = store.save({"name": "walk", "action": "walk", "view": "front",
                            "description": "同名冲突用例", "pose_config": {"bob": 1}})
        self.assertEqual(saved["name"], "walk")  # 自定义命名空间内合法
        # 与内置动作清单互不读写：内置 ACTIONS 不受存储影响
        self.assertIn("walk", ACTIONS)
        self.assertEqual(store.get("walk")["action"], "walk")


if __name__ == "__main__":
    unittest.main()
