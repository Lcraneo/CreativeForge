"""Regression tests for the fixed DashScope video model (offline).

视频模型在动画工作台 / 试玩舞台（单动作 / 批量补齐）统一固定为
``wan2.2-i2v-flash``：``video_model``、``video_model_final`` 与
``model_override`` 都不影响实际请求，也不会自动回退到 plus / turbo。
网络重试、Key 切换、额度/鉴权/审核错误处理仍保持原语义。
"""

import tempfile
import unittest
from unittest import mock

import httpx

from studio.backend.model_service import service
from studio.backend.model_service.service import VIDEO_MODEL


def _settings(video_model="", **extra):
    data = {
        "api_key": "test-key",
        "model": "image-model",
        "video_model": video_model,
        "video_size": "1280*720",
        "video_prompt_extend": False,
        "negative_prompt": "",
        "timeout": 10,
    }
    data.update(extra)
    return data


def _ok_response(task_id="task-1"):
    return httpx.Response(
        200, json={"output": {"task_id": task_id, "task_status": "PENDING"}}
    )


class VideoModelFallbackTests(unittest.TestCase):
    def _generate(self, posts, *, settings=None, model_override=None):
        with tempfile.TemporaryDirectory() as cache_dir:
            with (
                mock.patch.object(service, "_VIDEO_CACHE_DIR", cache_dir),
                mock.patch.object(service.httpx, "post", side_effect=posts) as post,
                mock.patch.object(
                    service, "poll_video_task", return_value="https://video.test/a.mp4"
                ),
                mock.patch.object(
                    service.httpx,
                    "get",
                    return_value=httpx.Response(
                        200,
                        content=b"video-bytes",
                        request=httpx.Request("GET", "https://video.test/a.mp4"),
                    ),
                ),
                mock.patch("studio.backend.model_service.usage.record_usage") as usage,
                mock.patch.object(service.time, "sleep"),
            ):
                result = service.generate_video(
                    settings or _settings(),
                    "walk in place",
                    b"source-image",
                    model_override=model_override,
                )
        return result, post.call_args_list, usage

    def test_default_settings_use_flash(self):
        (content, model), calls, usage = self._generate([_ok_response()])

        self.assertEqual(content, b"video-bytes")
        self.assertEqual(model, VIDEO_MODEL)
        self.assertEqual(model, "wan2.2-i2v-flash")
        self.assertEqual(
            [call.kwargs["json"]["model"] for call in calls], ["wan2.2-i2v-flash"]
        )
        usage.assert_called_once_with("video", "wan2.2-i2v-flash")

    def test_configured_plus_still_uses_flash(self):
        (_, model), calls, _ = self._generate(
            [_ok_response()], settings=_settings("wan2.2-i2v-plus")
        )

        self.assertEqual(model, "wan2.2-i2v-flash")
        self.assertEqual(
            [call.kwargs["json"]["model"] for call in calls], ["wan2.2-i2v-flash"]
        )

    def test_model_override_plus_still_uses_flash(self):
        (_, model), calls, _ = self._generate(
            [_ok_response()], model_override="wan2.2-i2v-plus"
        )

        self.assertEqual(model, "wan2.2-i2v-flash")
        self.assertEqual(
            [call.kwargs["json"]["model"] for call in calls], ["wan2.2-i2v-flash"]
        )

    def test_final_quality_still_uses_flash(self):
        """final_quality=true 走 create_video 的定稿档路径，实际请求仍是 flash。"""

        from studio.backend.animation_service import service as anim_service

        settings = _settings(
            "wan2.2-i2v-plus", video_model_final="wan2.2-i2v-plus"
        )
        with tempfile.TemporaryDirectory() as cache_dir:
            with (
                mock.patch.object(service, "_VIDEO_CACHE_DIR", cache_dir),
                mock.patch.object(
                    service.httpx, "post", return_value=_ok_response()
                ) as post,
                mock.patch.object(
                    service, "poll_video_task", return_value="https://video.test/a.mp4"
                ),
                mock.patch.object(
                    service.httpx,
                    "get",
                    return_value=httpx.Response(
                        200,
                        content=b"video-bytes",
                        request=httpx.Request("GET", "https://video.test/a.mp4"),
                    ),
                ),
                mock.patch("studio.backend.model_service.usage.record_usage") as usage,
                mock.patch.object(service.time, "sleep"),
                mock.patch.object(
                    anim_service, "ai_enhance_motion_prompt", return_value="walk in place"
                ),
                mock.patch.object(
                    anim_service.AnimationService, "_crop_to_subject",
                    return_value=(b"source-image", None),
                ),
                mock.patch.object(
                    anim_service.AnimationService, "_slice_video",
                    return_value=([], {"fps": 12}),
                ),
                mock.patch.object(
                    anim_service.AnimationService, "_deliver_video_mp4", return_value=None
                ),
                mock.patch.object(
                    anim_service.AnimationService, "_persist", return_value={"urls": {}}
                ),
                mock.patch.object(anim_service.AnimationService, "_write"),
                mock.patch(
                    "studio.backend.animation_service.motion_qa.post_validate",
                    return_value={},
                ),
                mock.patch("artgen.compose_animation", return_value={}),
            ):
                with tempfile.TemporaryDirectory() as work_dir:
                    meta = anim_service.AnimationService(work_dir).create_video(
                        b"source-image",
                        settings,
                        action="walk",
                        final_quality=True,
                        equipment_aware=False,
                    )

        self.assertEqual(meta["video_model"], "wan2.2-i2v-flash")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "wan2.2-i2v-flash")
        usage.assert_called_once_with("video", "wan2.2-i2v-flash")

    def test_quota_error_switches_key_but_never_plus_or_turbo(self):
        quota = httpx.Response(
            403,
            text='{"code":"AllocationQuota.FreeTierOnly","message":"Free quota exhausted."}',
        )
        settings = _settings("wan2.2-i2v-plus", api_key_pool=["backup-key"])
        (content, model), calls, _ = self._generate(
            [quota, _ok_response("task-2")], settings=settings
        )

        self.assertEqual(content, b"video-bytes")
        self.assertEqual(model, "wan2.2-i2v-flash")
        self.assertEqual(
            [call.kwargs["json"]["model"] for call in calls],
            ["wan2.2-i2v-flash", "wan2.2-i2v-flash"],
        )
        self.assertEqual(
            [call.kwargs["headers"]["Authorization"] for call in calls],
            ["Bearer test-key", "Bearer backup-key"],
        )

    def test_transport_error_retries_same_flash_model(self):
        (content, model), calls, _ = self._generate(
            [httpx.ConnectError("connection reset"), _ok_response()]
        )

        self.assertEqual(content, b"video-bytes")
        self.assertEqual(model, "wan2.2-i2v-flash")
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            all(
                call.kwargs["json"]["model"] == "wan2.2-i2v-flash" for call in calls
            )
        )


if __name__ == "__main__":
    unittest.main()
