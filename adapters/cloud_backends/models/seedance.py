"""火山方舟 ARK · Seedance 视频生成（CG 视频云端通道）。

接口形态（方舟内容生成任务）：

- 创建：``POST {base}/contents/generations/tasks`` → ``{"id": "<task>"}``
- 轮询：``GET {base}/contents/generations/tasks/{id}`` → ``status`` + ``content.video_url``
- 输入：``content`` 数组，文本项 ``{"type": "text", "text": ...}``，
  首帧图 ``{"type": "image_url", "image_url": {"url": ...}}``

产物链接短期有效，因此和 3D 一样**必须即时落盘**。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..client import cloud_client
from .base import BaseCloudModel

log = logging.getLogger("adapters.cloud_backends.seedance")

__all__ = ["SeedanceModel", "MODEL_OPTIONS", "DEFAULT_MODEL"]

MODEL_OPTIONS = (
    "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-t2v-250428",
    "doubao-seedance-1-0-lite-i2v-250428",
)
DEFAULT_MODEL = "doubao-seedance-1-0-pro-250528"

DONE_STATES = ("succeeded", "success", "completed")
FAILED_STATES = ("failed", "canceled", "cancelled", "expired")


class SeedanceModel(BaseCloudModel):
    """Seedance 文生视频 / 图生视频。"""

    PROVIDER = "ark"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "mp4"
    ENV_KEY = "ARK_API_KEY"
    DEFAULT_TASK_TIMEOUT = 900.0

    def __init__(
        self,
        *,
        ratio: str = "16:9",
        duration: float = 5.0,
        poll_interval: float = 5.0,
        **kwargs,
    ):
        super().__init__(poll_interval=poll_interval, **kwargs)
        self.ratio = ratio
        self.duration = duration

    # ── 协议 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _content_of(task: dict) -> dict:
        content = task.get("content")
        return content if isinstance(content, dict) else {}

    @staticmethod
    def _video_url(task: dict) -> str:
        content = SeedanceModel._content_of(task)
        url = content.get("video_url") or content.get("url")
        if isinstance(url, dict):
            url = url.get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
        raise cloud_client.CloudAPIError(
            f"任务成功但没有视频 URL：content={content!r}",
            provider="ark",
            task_id=str(task.get("id") or ""),
        )

    def _fetch_task(self, task_id: str) -> dict:
        payload = self.client.request("GET", f"/contents/generations/tasks/{task_id}")
        if not isinstance(payload, dict):
            raise cloud_client.CloudAPIError(
                f"任务响应不是对象：{payload!r}", provider=self.PROVIDER, task_id=task_id
            )
        return payload

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        prompt: str = "",
        image_url: Optional[str] = None,
        image: Any = None,
        duration: float | None = None,
        ratio: Optional[str] = None,
        seed: int | None = None,
        **provider_kwargs,
    ) -> bytes:
        """生成视频并返回 MP4 字节（有首帧图即走图生视频）。"""

        text = (prompt or "").strip()
        if image is not None and not image_url:
            raise ValueError("Seedance 通道只接受公网 image_url，本地图片请先上传对象存储")
        if not text and not image_url:
            raise ValueError("Seedance 需要 prompt 或 image_url 之一")

        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        payload: dict[str, Any] = {
            "model": self.model,
            "content": content,
            "ratio": ratio or self.ratio,
            "duration": int(duration or self.duration),
        }
        if seed is not None:
            payload["seed"] = int(seed)
        payload.update(provider_kwargs)

        cache_key = self._cache_key(payload=payload)
        cached = self._cache.get(cache_key, ext=self.OUTPUT_EXT)
        if cached is not None:
            self.last_call_info = {
                "provider": self.PROVIDER,
                "model": self.model,
                "cached": True,
                "cache_key": cache_key,
                "bytes": len(cached),
            }
            return cached

        created = self.client.request(
            "POST", "/contents/generations/tasks", json_body=payload
        )
        task_id = ""
        if isinstance(created, dict):
            task_id = str(created.get("id") or created.get("task_id") or "")
        if not task_id:
            raise cloud_client.CloudAPIError(
                f"创建任务成功但未返回 id：{created!r}", provider=self.PROVIDER
            )

        task = cloud_client.poll_task(
            lambda: self._fetch_task(task_id),
            task_id=task_id,
            timeout=self.task_timeout,
            poll_interval=self.poll_interval,
            done_states=DONE_STATES,
            failed_states=FAILED_STATES,
            status_key="status",
            provider=self.PROVIDER,
            sleep=self._sleep,
        )

        data = self._fetch_bytes(self._video_url(task), cache_key)
        self.last_call_info.update(
            {
                "provider": self.PROVIDER,
                "model": self.model,
                "task_id": task_id,
                "cached": False,
                "cache_key": cache_key,
                "bytes": len(data),
                "duration_s": float(payload["duration"]),
                "ratio": payload["ratio"],
            }
        )
        log.info(
            "[seedance] task=%s model=%s bytes=%s",
            task_id,
            self.model,
            len(data),
        )
        return data
