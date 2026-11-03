"""动画任务落盘回归：重启标记 interrupted、终态保留、TTL 丢弃、损坏容错。"""

import tempfile
import time
import unittest
from pathlib import Path

from studio.backend.animation_service import task_store


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "tasks.json")

    def test_save_restore_roundtrip_marks_running_interrupted(self):
        now = time.time()
        video = {"t1": {"id": "t1", "status": "running", "stage": "video", "created_at": now}}
        batch = {"b1": {"id": "b1", "status": "running", "created_at": now,
                        "tasks": [{"action": "walk", "status": "generating"},
                                  {"action": "run", "status": "pending"},
                                  {"action": "idle", "status": "done"}]}}
        task_store.save(video, batch, path=self.path)

        restored_video: dict = {}
        restored_batch: dict = {}
        count = task_store.restore(restored_video, restored_batch, path=self.path)
        self.assertEqual(count, 2)

        task = restored_video["t1"]
        self.assertEqual(task["status"], "interrupted")
        self.assertEqual(task["error_kind"], "interrupted")
        self.assertTrue(task["error"])

        restored = restored_batch["b1"]
        self.assertEqual(restored["status"], "interrupted")
        statuses = {entry["action"]: entry["status"] for entry in restored["tasks"]}
        self.assertEqual(statuses, {"walk": "interrupted", "run": "interrupted", "idle": "done"})

    def test_terminal_tasks_survive_restart_unchanged(self):
        video = {"t1": {"id": "t1", "status": "done", "stage": "done",
                        "created_at": time.time(), "result": {"id": "anim1"}}}
        task_store.save(video, {}, path=self.path)
        restored: dict = {}
        task_store.restore(restored, {}, path=self.path)
        self.assertEqual(restored["t1"]["status"], "done")
        self.assertEqual(restored["t1"]["result"], {"id": "anim1"})

    def test_stale_entries_beyond_ttl_are_dropped(self):
        old = time.time() - 7200
        video = {"t1": {"id": "t1", "status": "running", "created_at": old}}
        task_store.save(video, {}, path=self.path)
        restored: dict = {}
        count = task_store.restore(restored, {}, path=self.path, max_age=3600.0)
        self.assertEqual(count, 0)
        self.assertEqual(restored, {})

    def test_malformed_entries_are_skipped(self):
        now = time.time()
        payload = {"saved_at": now,
                   "video_tasks": {"bad": {"id": "other", "status": "running"}},
                   "action_batches": {"b1": {"id": "b1", "status": "running", "created_at": now}}}
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.path).write_text(
            __import__("json").dumps(payload), encoding="utf-8"
        )
        restored_video: dict = {}
        restored_batch: dict = {}
        count = task_store.restore(restored_video, restored_batch, path=self.path)
        self.assertEqual(count, 1)
        self.assertNotIn("bad", restored_video)
        self.assertIn("b1", restored_batch)

    def test_corrupt_file_restores_nothing(self):
        Path(self.path).write_text("{broken", encoding="utf-8")
        restored_video: dict = {}
        restored_batch: dict = {}
        count = task_store.restore(restored_video, restored_batch, path=self.path)
        self.assertEqual(count, 0)
        self.assertEqual(restored_video, {})
        self.assertEqual(restored_batch, {})


if __name__ == "__main__":
    unittest.main()
