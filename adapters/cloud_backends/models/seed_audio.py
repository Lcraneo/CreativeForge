"""Seed Audio（音频能力云端通道）：单 wrapper 双槽 —— 对白 / 音效。

接口按 OpenAI 兼容的语音合成协议实现（``POST /audio/speech``）：

- 请求：``{"model", "input", "voice", "response_format", "speed"}``
- 响应：音频二进制（``audio/mpeg`` 等），**不返回 JSON**

厂商若提供独立音效接口，只需在面板里把 ``base_url`` 指向对应网关，
并把 ``model`` / ``path`` 改成该网关的取值；协议形状保持不变。
"""

from __future__ import annotations

import logging
from typing import Any

from ..client import cloud_client
from .base import BaseCloudModel

log = logging.getLogger("adapters.cloud_backends.seed_audio")

__all__ = ["SeedAudioModel", "MODEL_OPTIONS", "DEFAULT_MODEL", "AUDIO_KINDS"]

MODEL_OPTIONS = ("seed-tts-1.0",)
DEFAULT_MODEL = "seed-tts-1.0"
AUDIO_KINDS = ("dialogue", "sfx")


class SeedAudioModel(BaseCloudModel):
    """对白语音合成与短音效生成。"""

    PROVIDER = "seed-audio"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "mp3"
    ENV_KEY = "SEED_AUDIO_API_KEY"
    DEFAULT_TASK_TIMEOUT = 120.0

    def __init__(
        self,
        *,
        voice: str = "zh_female_qingxin",
        path: str = "/audio/speech",
        speed: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.voice = voice
        self.path = path if path.startswith("/") else f"/{path}"
        self.speed = speed

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        kind: str = "dialogue",
        text: str = "",
        prompt: str = "",
        voice: str | None = None,
        speed: float | None = None,
        **provider_kwargs,
    ) -> bytes:
        """按槽位生成音频：``dialogue`` 念文本，``sfx`` 用提示词描述音效。"""

        if kind not in AUDIO_KINDS:
            raise ValueError(f"kind 只能是 {'/'.join(AUDIO_KINDS)}：{kind!r}")
        if kind == "dialogue":
            content = (text or "").strip()
            if not content:
                raise ValueError("dialogue 槽位需要非空 text")
        else:
            content = (prompt or text or "").strip()
            if not content:
                raise ValueError("sfx 槽位需要非空 prompt（音效描述）")

        payload: dict[str, Any] = {
            "model": self.model,
            "input": content,
            "voice": voice or self.voice,
            "response_format": self.OUTPUT_EXT,
            "speed": float(speed if speed is not None else self.speed),
        }
        payload.update(provider_kwargs)

        cache_key = self._cache_key(kind=kind, payload=payload)
        cached = self._cache.get(cache_key, ext=self.OUTPUT_EXT)
        if cached is not None:
            self.last_call_info = {
                "provider": self.PROVIDER,
                "model": self.model,
                "kind": kind,
                "cached": True,
                "cache_key": cache_key,
                "bytes": len(cached),
            }
            return cached

        data = self.client.request_bytes("POST", self.path, json_body=payload)
        if not data:
            raise cloud_client.CloudAPIError("音频接口返回空响应", provider=self.PROVIDER)
        self._cache.put(cache_key, data, ext=self.OUTPUT_EXT)
        self.last_call_info.update(
            {
                "provider": self.PROVIDER,
                "model": self.model,
                "kind": kind,
                "cached": False,
                "cache_key": cache_key,
                "bytes": len(data),
            }
        )
        log.info("[seed-audio] kind=%s model=%s bytes=%s", kind, self.model, len(data))
        return data

    def speak(self, text: str, *, voice: str | None = None) -> bytes:
        """对白槽位的语义化入口。"""

        return self.infer(kind="dialogue", text=text, voice=voice)

    def sfx(self, prompt: str) -> bytes:
        """音效槽位的语义化入口。"""

        return self.infer(kind="sfx", prompt=prompt)
