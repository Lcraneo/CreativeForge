"""Regression tests for resilient DashScope video-task polling (offline)."""

import unittest
from unittest import mock

import httpx

from studio.backend.model_service import service


class _Response:
    status_code = 200

    def json(self):
        return {"output": {"task_status": "SUCCEEDED", "video_url": "https://video.test/a.mp4"}}


class VideoPollingTests(unittest.TestCase):
    def test_transient_status_timeout_keeps_polling_same_task(self):
        """A submitted remote task is not recreated merely because one poll drops."""

        with mock.patch.object(
            service.httpx,
            "get",
            side_effect=[httpx.ReadTimeout("temporary"), _Response()],
        ) as get, mock.patch.object(service.time, "sleep"):
            url = service.poll_video_task("key", "task-1", 30)

        self.assertEqual(url, "https://video.test/a.mp4")
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
