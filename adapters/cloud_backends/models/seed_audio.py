"""Seed Audio（音频能力云端通道）：单 wrapper 双槽 —— 对白 / 音效。

协议已对照 GameFactory-3A ``models/gen_audio/seed_audio_model.py`` 实码核验：

- 创建：``POST {base}/api/v3/tts/create``，**同步**返回 JSON（无轮询）
- 请求体：``{"model", "text_prompt", "audio_config": {...}, "references": [...]}``
  - ``audio_config``：``format`` / ``sample_rate`` / ``speech_rate`` /
    ``loudness_rate`` / ``pitch_rate``（``subtitle`` 仅在开启时发送）
  - ``references``：音色参考 ``{"speaker": "<资源 id>"}`` 或参考音频
    ``{"audio_data": "<wav base64>"}``（≤10 MiB）
- 响应：``audio``（base64）或 ``url``（音频下载链接）二者取一；外层可能有
  ``{"body": {...}}`` 信封与 ``code``/``status`` 状态位
- 上限：``text_prompt`` ≤ 3000 字符；``speech_rate`` ∈ [-50, 100]，
  ``loudness_rate`` ∈ [-50, 100]，``pitch_rate`` ∈ [-12, 12]

对白模式把文本（含 ``instruct`` / ``language`` 指令）拼进 ``text_prompt``；
音效模式用提示词描述音效，可附加时长提示。历史调用方的 ``speed``（倍速）
映射为 ``speech_rate``，``voice`` 名映射为 ``{"speaker": ...}`` 参考。
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from typing import Any, Optional

from ..client import cloud_client
from .base import BaseCloudModel, merge_provider_kwargs

log = logging.getLogger("adapters.cloud_backends.seed_audio")

__all__ = ["SeedAudioModel", "MODEL_OPTIONS", "DEFAULT_MODEL", "AUDIO_KINDS"]

MODEL_OPTIONS = ("seed-audio-1.0",)
DEFAULT_MODEL = "seed-audio-1.0"
AUDIO_KINDS = ("dialogue", "sfx")

CREATE_PATH = "/api/v3/tts/create"
#: 与 GF 实码一致的默认根地址；面板留空时仍能工作
DEFAULT_API_BASE = "https://openspeech.bytedance.com"
SUPPORTED_MODES = ("dialogue", "sound_effect")
ALLOWED_SAMPLE_RATES = (8000, 16000, 24000, 32000, 44100, 48000)
REFERENCE_MAX_BYTES = 10 * 1024 * 1024
TEXT_PROMPT_MAX_CHARS = 3000

#: ``code`` / ``status`` 里表示成功的取值（不同网关措辞不一，全部放行）
_OK_CODES = (None, 0, 200, "0", "200", "success", "Success")


class SeedAudioModel(BaseCloudModel):
    """对白语音合成与短音效生成（同步 TTS）。"""

    PROVIDER = "seed-audio"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "wav"
    ENV_KEY = "SEED_AUDIO_API_KEY"
    DEFAULT_TASK_TIMEOUT = 120.0

    def __init__(
        self,
        *,
        speaker_id: str = "",
        sample_rate: int = 24_000,
        output_format: str = "wav",
        speech_rate: int = 0,
        loudness_rate: int = 0,
        pitch_rate: int = 0,
        enable_subtitle: bool = False,
        path: str = CREATE_PATH,
        **kwargs,
    ):
        super().__init__(**kwargs)
        # base_url 留空时回落到官方默认根地址（GF 同口径），否则音频能力
        # 会在第一次请求时报「未配置 base_url」而完全不可用
        self.api_base = (
            self.api_base or os.environ.get("SEED_AUDIO_API_BASE") or DEFAULT_API_BASE
        ).rstrip("/")
        self.speaker_id = (speaker_id or os.environ.get("SEED_AUDIO_SPEAKER_ID", "")).strip()
        self.sample_rate = int(sample_rate)
        self.speech_rate = int(speech_rate)
        self.loudness_rate = int(loudness_rate)
        self.pitch_rate = int(pitch_rate)
        self.enable_subtitle = bool(enable_subtitle)
        self.path = path if path.startswith("/") else f"/{path}"
        if output_format.lower().lstrip(".") != "wav":
            raise ValueError(
                "Seed Audio 通道要求 output_format='wav'，以便解析时长并保持产物契约"
            )
        if self.sample_rate not in ALLOWED_SAMPLE_RATES:
            raise ValueError(f"不支持的 sample_rate：{self.sample_rate}")
        if not -50 <= self.speech_rate <= 100:
            raise ValueError("speech_rate 必须在 [-50, 100]")
        if not -50 <= self.loudness_rate <= 100:
            raise ValueError("loudness_rate 必须在 [-50, 100]")
        if not -12 <= self.pitch_rate <= 12:
            raise ValueError("pitch_rate 必须在 [-12, 12]")

    # ── text_prompt 组装 ──────────────────────────────────────────────────

    def _text_prompt(
        self,
        *,
        mode: str,
        text: str,
        prompt: str,
        instruct: str,
        language: str,
        duration_sec: Optional[float],
    ) -> str:
        if mode == "dialogue":
            value = (text or prompt or "").strip()
            if not value:
                raise ValueError("dialogue 槽位需要非空 text")
            directions = []
            if instruct.strip():
                directions.append(instruct.strip())
            if language and language.lower() != "auto":
                directions.append(f"Speak in {language}.")
            if directions:
                return f"{value}\nVoice direction: {' '.join(directions)}"
            return value

        value = (prompt or text or "").strip()
        if not value:
            raise ValueError("sfx 槽位需要非空 prompt（音效描述）")
        if duration_sec is not None:
            duration = float(duration_sec)
            if not 0 < duration <= 120:
                raise ValueError("duration_sec 必须大于 0 且不超过 120")
            value = f"{value}. Approximately {duration:g} seconds long."
        return value

    # ── 载荷 ──────────────────────────────────────────────────────────────

    def _payload(
        self,
        *,
        mode: str,
        text_prompt: str,
        speech_rate: int,
        reference_audio: Optional[bytes],
        speaker: str,
        provider_kwargs: dict,
    ) -> tuple[dict, Optional[str]]:
        audio_config: dict[str, Any] = {
            "format": "wav",
            "sample_rate": self.sample_rate,
            "speech_rate": speech_rate,
            "loudness_rate": self.loudness_rate,
            "pitch_rate": self.pitch_rate,
        }
        if self.enable_subtitle:
            audio_config["subtitle"] = True
        payload: dict[str, Any] = {
            "model": self.model,
            "text_prompt": text_prompt,
            "audio_config": audio_config,
        }

        reference_hash: Optional[str] = None
        if reference_audio is not None:
            if len(reference_audio) > REFERENCE_MAX_BYTES:
                raise ValueError(
                    f"参考音频 {len(reference_audio)} 字节，超过 10 MiB 上限"
                )
            reference_hash = cloud_client.bytes_hash(reference_audio)
            payload["references"] = [
                {"audio_data": base64.b64encode(reference_audio).decode("ascii")}
            ]
        elif speaker:
            payload["references"] = [{"speaker": speaker}]

        # GF kwargs 保护模式：None 不透传、核心字段不被覆盖、新增键原样追加
        merge_provider_kwargs(payload, provider_kwargs)
        return payload, reference_hash

    @staticmethod
    def _response_body(response: Any) -> dict:
        """解 ``{"body": {...}}`` 信封；``code``/``status`` 非成功即终态错误。"""

        if not isinstance(response, dict):
            raise cloud_client.CloudAPIError(
                f"Seed Audio 响应不是对象：{type(response).__name__}",
                provider="seed-audio",
            )
        body = response.get("body") if isinstance(response.get("body"), dict) else response
        code = body.get("code", response.get("status", 200))
        if code not in _OK_CODES:
            raise cloud_client.CloudAPIRequestError(
                f"Seed Audio 拒绝了生成请求：code={code!r}, message={body.get('message')!r}",
                provider="seed-audio",
                payload=response,
            )
        return body

    @staticmethod
    def _wav_duration(data: bytes) -> Optional[float]:
        """用标准库 ``wave`` 读时长；非 WAV 产物返回 ``None``（不伪造）。"""

        import io
        import wave

        try:
            with wave.open(io.BytesIO(data)) as handle:
                rate = handle.getframerate()
                if rate <= 0:
                    return None
                return handle.getnframes() / rate
        except Exception:  # noqa: BLE001 - 产物格式不受控
            return None

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        kind: str = "dialogue",
        text: str = "",
        prompt: str = "",
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        instruct: str = "",
        language: str = "",
        duration_sec: Optional[float] = None,
        reference_audio: Optional[bytes] = None,
        **provider_kwargs,
    ) -> bytes:
        """按槽位生成音频：``dialogue`` 念文本，``sfx`` 用提示词描述音效。

        Args:
            voice: 音色资源 id（历史参数），映射为 ``references=[{"speaker": ...}]``。
            speed: 历史倍速参数，映射为 ``speech_rate``（1.0 → 0）。
            instruct / language: 对白模式的语音方向指令，拼进 ``text_prompt``。
            duration_sec: 音效模式的时长提示（≤120 秒）。
            reference_audio: WAV 参考音频字节（≤10 MiB），走 ``audio_data`` 参考。
        """

        if kind not in AUDIO_KINDS:
            raise ValueError(f"kind 只能是 {'/'.join(AUDIO_KINDS)}：{kind!r}")
        mode = "dialogue" if kind == "dialogue" else "sound_effect"

        text_prompt = self._text_prompt(
            mode=mode,
            text=text,
            prompt=prompt,
            instruct=instruct,
            language=language,
            duration_sec=duration_sec,
        )
        if reference_audio is not None and "@Audio1" not in text_prompt:
            text_prompt = f"Use @Audio1 as the voice reference. {text_prompt}"
        if len(text_prompt) > TEXT_PROMPT_MAX_CHARS:
            raise ValueError(
                f"text_prompt 超过 {TEXT_PROMPT_MAX_CHARS} 字符上限（当前 {len(text_prompt)}）"
            )

        speech_rate = self.speech_rate
        if speed is not None:
            speech_rate = max(-50, min(100, int(round((float(speed) - 1.0) * 50))))

        payload, reference_hash = self._payload(
            mode=mode,
            text_prompt=text_prompt,
            speech_rate=speech_rate,
            reference_audio=reference_audio,
            speaker=(voice or "").strip() or self.speaker_id,
            provider_kwargs=provider_kwargs,
        )

        # 缓存键不含参考音频本体（以 sha256 代替），避免大对象进哈希
        cache_description = {
            "mode": mode,
            "payload": {
                **payload,
                "references": (
                    [{"audio_sha256": reference_hash}]
                    if reference_hash
                    else payload.get("references")
                ),
            },
        }
        cache_key = self._cache_key(**cache_description)
        cached = self._cache.get(cache_key, ext=self.OUTPUT_EXT)
        if cached is not None:
            self.last_call_info = {
                "provider": self.PROVIDER,
                "model": self.model,
                "kind": kind,
                "mode": mode,
                "cached": True,
                "cache_key": cache_key,
                "bytes": len(cached),
                "duration_sec": self._wav_duration(cached),
            }
            return cached

        response = self.client.request("POST", self.path, json_body=payload)
        body = self._response_body(response)

        encoded = body.get("audio")
        data: Optional[bytes] = None
        if isinstance(encoded, str) and encoded:
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise cloud_client.CloudAPIError(
                    f"Seed Audio 响应里的 base64 音频解码失败：{error}",
                    provider=self.PROVIDER,
                    payload=response,
                ) from error
        else:
            audio_url = body.get("url")
            if not isinstance(audio_url, str) or not audio_url.startswith("http"):
                raise cloud_client.CloudAPIError(
                    "Seed Audio 响应既没有 base64 audio 也没有合法 url",
                    provider=self.PROVIDER,
                    payload=response,
                )
            data = self.client.download(audio_url, max_bytes=100 * 1024 * 1024)

        self._cache.put(cache_key, data, ext=self.OUTPUT_EXT)
        self.last_call_info = {
            "provider": self.PROVIDER,
            "model": self.model,
            "kind": kind,
            "mode": mode,
            "cached": False,
            "cache_key": cache_key,
            "bytes": len(data),
            "duration_sec": self._wav_duration(data),
            "response_duration_sec": body.get("original_duration") or body.get("duration"),
        }
        log.info(
            "[seed-audio] mode=%s model=%s bytes=%s duration=%s",
            mode,
            self.model,
            len(data),
            self.last_call_info.get("duration_sec"),
        )
        return data

    def speak(self, text: str, *, voice: str | None = None) -> bytes:
        """对白槽位的语义化入口。"""

        return self.infer(kind="dialogue", text=text, voice=voice)

    def sfx(self, prompt: str) -> bytes:
        """音效槽位的语义化入口。"""

        return self.infer(kind="sfx", prompt=prompt)
