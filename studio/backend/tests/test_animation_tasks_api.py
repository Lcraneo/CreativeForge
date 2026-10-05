"""动画生成任务的幂等路由回归：同键运行中复用快照，不重复入队。"""

import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.routes import _ANIM_TASK_IDEMPOTENCY, build_router


def _snapshot(task_id: str, status: str = "running") -> dict:
    return {"id": task_id, "status": status, "stage": "prompt", "progress": 5.0}


class AnimationTaskIdempotencyTests(unittest.TestCase):
    def setUp(self):
        _ANIM_TASK_IDEMPOTENCY._entries.clear()

    def _app(self, service: Mock) -> FastAPI:
        runtime = Mock()
        runtime.model_settings.effective.return_value = {
            "enabled": True,
            "api_key": "k",
            "use_video": True,
        }
        app = FastAPI()
        app.include_router(build_router(runtime))
        return app

    def test_same_key_while_running_returns_same_task_without_requeue(self):
        service = Mock()
        service._asset_render.return_value = b"png-bytes"
        service.start_video_task.side_effect = [
            _snapshot("task-1"),
            AssertionError("must not enqueue twice"),
        ]
        with patch("studio.backend.animation_service.service.AnimationService",
                   return_value=service):
            client = TestClient(self._app(service))
            body = {"action": "walk", "use_video": True}
            first = client.post("/api/animation/tasks", json=body,
                                headers={"Idempotency-Key": "key-1"})
            self.assertEqual(first.status_code, 202)
            self.assertEqual(first.json()["task_id"], "task-1")
            second = client.post("/api/animation/tasks", json=body,
                                 headers={"Idempotency-Key": "key-1"})
            self.assertEqual(second.status_code, 202)
            self.assertEqual(second.json()["task_id"], "task-1")
            service.start_video_task.assert_called_once()

    def test_terminal_task_does_not_block_new_submission(self):
        service = Mock()
        service._asset_render.return_value = b"png-bytes"
        service.start_video_task.side_effect = [
            _snapshot("task-1", status="failed"),
            _snapshot("task-2"),
        ]
        with patch("studio.backend.animation_service.service.AnimationService",
                   return_value=service):
            client = TestClient(self._app(service))
            headers = {"Idempotency-Key": "key-1"}
            self.assertEqual(
                client.post("/api/animation/tasks", json={"action": "walk"}, headers=headers)
                .json()["task_id"],
                "task-1",
            )
            self.assertEqual(
                client.post("/api/animation/tasks", json={"action": "walk"}, headers=headers)
                .json()["task_id"],
                "task-2",
            )
            self.assertEqual(service.start_video_task.call_count, 2)

    def test_missing_key_behaves_as_before(self):
        service = Mock()
        service._asset_render.return_value = b"png-bytes"
        service.start_video_task.side_effect = [
            _snapshot("task-1"),
            _snapshot("task-2"),
        ]
        with patch("studio.backend.animation_service.service.AnimationService",
                   return_value=service):
            client = TestClient(self._app(service))
            body = {"action": "walk"}
            self.assertEqual(client.post("/api/animation/tasks", json=body).json()["task_id"],
                             "task-1")
            self.assertEqual(client.post("/api/animation/tasks", json=body).json()["task_id"],
                             "task-2")


if __name__ == "__main__":
    unittest.main()
