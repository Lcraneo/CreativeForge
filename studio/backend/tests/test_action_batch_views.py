"""动作批次视角与恢复语义回归（离线）。

覆盖实际故障链：正面 walk 不能让侧面 walk 被跳过；同一批必须按动作携带
不同视角与源图；重复请求复用运行中的批次；线程异常必须落到失败终态。
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from studio.backend.animation_service.service import AnimationService


def _write_video_meta(
    directory: str,
    animation_id: str,
    *,
    asset_id: str,
    action: str,
    view: str,
    frames: int = 5,
) -> None:
    urls = []
    for index in range(frames):
        name = f"{animation_id}_f{index:02}.png"
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(b"png")
        urls.append(f"/api/animation/{name}")
    meta = {
        "id": animation_id,
        "source": "video",
        "asset_id": asset_id,
        "requested_action": action,
        "view": view,
        "frame_urls": urls,
        "created_at": 1,
    }
    with open(os.path.join(directory, f"{animation_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False)


class ActionBatchViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = self.temp.name
        self.asset = "ast-view-test"
        self.service = AnimationService(self.directory)
        self.service.action_batches = {}

    def test_existing_ai_actions_requires_matching_view(self):
        _write_video_meta(
            self.directory,
            "walk-front",
            asset_id=self.asset,
            action="walk",
            view="front",
        )
        self.assertEqual(self.service.existing_ai_actions(self.asset), {"walk"})
        self.assertEqual(
            self.service.existing_ai_actions(self.asset, expected_views={"walk": "side"}),
            set(),
        )

        _write_video_meta(
            self.directory,
            "walk-side",
            asset_id=self.asset,
            action="walk",
            view="side",
        )
        self.assertEqual(
            self.service.existing_ai_actions(self.asset, expected_views={"walk": "side"}),
            {"walk"},
        )

    def test_front_walk_does_not_skip_side_walk(self):
        _write_video_meta(
            self.directory,
            "walk-front",
            asset_id=self.asset,
            action="walk",
            view="front",
        )
        with (
            patch("studio.backend.animation_service.service.threading.Thread"),
            patch("studio.backend.animation_service.service._persist_tasks"),
        ):
            batch_id = self.service.start_action_batch(
                self.asset,
                {"side": b"side-source"},
                {},
                actions=["walk"],
                views_by_action={"walk": "side"},
            )

        snapshot = self.service.action_batch_snapshot(batch_id)
        self.assertEqual(snapshot["total"], 1)
        self.assertEqual(snapshot["tasks"][0]["status"], "pending")
        self.assertEqual(snapshot["tasks"][0]["view"], "side")

    def test_mixed_views_are_kept_per_task(self):
        views = {
            "idle": "front",
            "walk": "side",
            "run": "side",
            "attack": "front",
            "jump": "side",
        }
        with (
            patch("studio.backend.animation_service.service.threading.Thread") as thread_cls,
            patch("studio.backend.animation_service.service._persist_tasks"),
        ):
            batch_id = self.service.start_action_batch(
                self.asset,
                {"front": b"front-source", "side": b"side-source"},
                {},
                actions=list(views),
                views_by_action=views,
                facing_by_view={"side": "left"},
            )

        snapshot = self.service.action_batch_snapshot(batch_id)
        self.assertEqual(snapshot["view"], "mixed")
        self.assertEqual(snapshot["total"], 5)
        self.assertEqual({task["action"]: task["view"] for task in snapshot["tasks"]}, views)
        target_args = thread_cls.call_args.kwargs["args"]
        self.assertEqual(
            target_args[2], {"front": b"front-source", "side": b"side-source"}
        )
        self.assertEqual(target_args[6], views)
        self.assertEqual(target_args[7], {"side": "left"})

    def test_duplicate_request_reuses_running_batch(self):
        with (
            patch("studio.backend.animation_service.service.threading.Thread"),
            patch("studio.backend.animation_service.service._persist_tasks"),
        ):
            first = self.service.start_action_batch(
                self.asset,
                {"side": b"side-source"},
                {},
                actions=["walk"],
                views_by_action={"walk": "side"},
            )
            second = self.service.start_action_batch(
                self.asset,
                {"side": b"side-source"},
                {},
                actions=["walk"],
                views_by_action={"walk": "side"},
            )

        self.assertEqual(first, second)

    def test_worker_failure_marks_batch_failed_instead_of_stuck_running(self):
        self.service.action_batches["broken"] = {
            "id": "broken",
            "asset_id": self.asset,
            "status": "running",
            "total": 1,
            "tasks": [{"action": "walk", "status": "pending", "view": "side"}],
        }
        with (
            patch.object(
                self.service,
                "_run_action_batch_impl",
                side_effect=RuntimeError("worker exploded"),
            ),
            patch("studio.backend.animation_service.service._persist_tasks"),
        ):
            self.service._run_action_batch(
                "broken",
                self.asset,
                {"side": b"side-source"},
                {},
                ["walk"],
                None,
                {"walk": "side"},
            )

        snapshot = self.service.action_batch_snapshot("broken")
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["tasks"][0]["status"], "failed")
        self.assertEqual(snapshot["tasks"][0]["error_kind"], "fatal")
        self.assertIn("worker exploded", snapshot["error"])


if __name__ == "__main__":
    unittest.main()
