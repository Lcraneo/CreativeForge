"""火山方舟 ARK · Seedream 图像生成（图像能力云端通道）。

接口要点（对齐方舟 OpenAI 兼容的 ``/images/generations``）：

- 创建：``POST {base}/images/generations``，同步返回图片 URL 或 base64
- 鉴权：``Authorization: Bearer <ARK_API_KEY>``，Key 复用模型广场 volcengine
- 尺寸：``size`` 形如 ``1024x1024``；模型支持的档位以控制台开通页为准

与对话模型不同，本接口是**同步**的：一次请求直接拿产物，不需要轮询。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..client import cloud_client
from .base import BaseCloudModel

log = logging.getLogger("adapters.cloud_backends.seedream")

__all__ = ["SeedreamModel", "MODEL_OPTIONS", "DEFAULT_MODEL"]

MODEL_OPTIONS = (
    "doubao-seedream-3-0-t2i",
    "doubao-seedream-4-0-250828",
)
DEFAULT_MODEL = "doubao-seedream-3-0-t2i"


class SeedreamModel(BaseCloudModel):
    """Seedream 文生图。"""

    PROVIDER = "ark"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "png"
    ENV_KEY = "ARK_API_KEY"
    DEFAULT_TASK_TIMEOUT = 120.0

    def __init__(self, *, size: str = "1024x1024", watermark: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.size = size
        self.watermark = watermark

    # ── 响应解析 ──────────────────────────────────────────────────────────

    @staticmethod
    def _first_image(resp: Any) -> tuple[str | None, str | None]:
        """返回 ``(url, b64_json)``；两者都没有即为协议异常。"""

        if not isinstance(resp, dict):
            raise cloud_client.CloudAPIError(
                f"响应不是对象：{type(resp).__name__}", provider="ark"
            )
        items = resp.get("data")
        if not isinstance(items, list) or not items:
            raise cloud_client.CloudAPIError(f"响应缺少 data：{resp!r}", provider="ark")
        first = items[0]
        if not isinstance(first, dict):
            raise cloud_client.CloudAPIError(f"data[0] 不是对象：{first!r}", provider="ark")
        url = first.get("url")
        b64 = first.get("b64_json")
        if not url and not b64:
            raise cloud_client.CloudAPIError(
                f"没有图片产物（可能是内容审核拦截）：{first!r}", provider="ark"
            )
        return (str(url) if url else None), (str(b64) if b64 else None)

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        prompt: str = "",
        size: Optional[str] = None,
        seed: int | None = None,
        **provider_kwargs,
    ) -> bytes:
        """文生图，返回 PNG/JPEG 原始字节。"""

        text = (prompt or "").strip()
        if not text:
            raise ValueError("Seedream 需要非空 prompt")
        if provider_kwargs.pop("image", None):
            raise ValueError("Seedream 通道只支持文生图，图生图请使用 DashScope 通道")

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": text,
            "size": size or self.size,
            "response_format": "url",
            "watermark": self.watermark,
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

        resp = self.client.request("POST", "/images/generations", json_body=payload)
        url, b64 = self._first_image(resp)
        if b64:
            import base64

            try:
                data = base64.b64decode(b64)
            except ValueError as error:
                raise cloud_client.CloudAPIError(
                    f"b64_json 解码失败：{error}", provider=self.PROVIDER
                ) from error
            self._cache.put(cache_key, data, ext=self.OUTPUT_EXT)
        else:
            data = self._fetch_bytes(str(url), cache_key)

        self.last_call_info.update(
            {
                "provider": self.PROVIDER,
                "model": self.model,
                "cached": False,
                "cache_key": cache_key,
                "bytes": len(data),
                "size": payload["size"],
            }
        )
        log.info("[seedream] model=%s size=%s bytes=%s", self.model, payload["size"], len(data))
        return data
