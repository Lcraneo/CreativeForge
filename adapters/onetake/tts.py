"""tts — 旁白语音合成：httpx 直调 DashScope qwen3-tts（零新依赖）。

管线职责：把 vo_script 的五段文本合成 wav 缓存文件（48k 混音由 audio.py
负责）。硬性纪律（产品规格）：
  * 多 API 密钥池自动轮换——额度/鉴权错误切下一把（复用 model_service 的
    Key 池与健康台账，与生图/视频同一套口径）；
  * 内容审核误报一次重试（DashScope 审核存在随机误杀，实测经验）；重试
    仍失败则放弃该段——文本固定，换 Key/换模型无意义；
  * 主力模型 qwen3-tts-instruct-flash（instructions 指令式风格控制，按拍
    定语气）；兜底 qwen-tts（不支持 instructions）。2026-10-03 实测两者
    均可用，产物 24kHz 单声道 16bit wav（audio.py 统一重采样 48k）；
  * 全部片段失败抛 VoUnavailable —— ShowcaseService 据此降级为纯音效版，
    出片永不因配音失败而失败。
缓存：sha1(model|voice|style|text) → wav 字节原样落盘，同文案永不二次计费。
"""

from __future__ import annotations

import hashlib
import logging
import os

import httpx

log = logging.getLogger("studio.showcase")

ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
TTS_MODEL = "qwen3-tts-instruct-flash"
FALLBACK_MODEL = "qwen-tts"
VOICE = "Cherry"
LANGUAGE = "Chinese"
REQUEST_TIMEOUT_S = 60.0


class VoUnavailable(RuntimeError):
    """全部旁白段合成失败（ShowcaseService 降级为纯音效的信号）。"""


def _classify(exc: Exception) -> str:
    """错误分类：优先复用 model_service 的统一口径，导入失败用本地近似。"""

    try:
        from studio.backend.model_service.service import classify_error

        return classify_error(exc)
    except Exception:  # noqa: BLE001
        text = str(exc).lower()
        if any(m in text for m in ("arrearage", "quota", "429", "throttling", "ratelimit")):
            return "quota"
        if any(m in text for m in ("401", "invalidapikey", "unauthorized", "403")):
            return "auth"
        if any(m in text for m in ("datainspection", "inappropriate", "sensitive", "moderation")):
            return "moderation"
        return "fatal"


def _note_key(key: str, ok: bool, kind: str | None = None) -> None:
    """Key 健康台账（复用 model_service，统计行为永不抛错）。"""

    try:
        from studio.backend.model_service.service import note_key_outcome

        note_key_outcome(key, ok, kind)
    except Exception:  # noqa: BLE001
        pass


def _request(key: str, model: str, text: str, instructions: str | None) -> tuple[bytes, int]:
    """单次合成：→ (wav 字节, 计费字符数)。任何失败抛异常。"""

    payload: dict = {
        "model": model,
        "input": {"text": text, "voice": VOICE, "language_type": LANGUAGE},
    }
    if instructions and "instruct" in model:
        payload["input"]["instructions"] = instructions
    response = httpx.post(
        ENDPOINT,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT_S,
    )
    if response.status_code != 200:
        raise RuntimeError("HTTP {}: {}".format(response.status_code, response.text[:220]))
    data = response.json()
    audio = (data.get("output") or {}).get("audio") or {}
    url = audio.get("url")
    if not url:
        raise RuntimeError("响应缺少 output.audio.url")
    chars = int((data.get("usage") or {}).get("characters") or 0)
    media = httpx.get(url, timeout=REQUEST_TIMEOUT_S)
    if media.status_code != 200 or len(media.content) < 44:
        raise RuntimeError("音频下载失败 HTTP {}".format(media.status_code))
    if media.content[:4] != b"RIFF" or media.content[8:12] != b"WAVE":
        raise RuntimeError("音频产物不是 wav（got {!r})".format(media.content[:4]))
    return media.content, chars


def _cache_path(cache_dir: str, seg: dict) -> str:
    digest = hashlib.sha1(
        "|".join([TTS_MODEL, VOICE, seg.get("style") or "", seg["text"]]).encode("utf-8")
    ).hexdigest()[:20]
    return os.path.join(cache_dir, digest + ".wav")


def _synthesize_segment(seg: dict, keys: list[str], cache_dir: str) -> tuple[str, bool, int] | None:
    """单段合成：→ (缓存路径, 是否缓存命中, 计费字符) | None（该段放弃）。"""

    cache = _cache_path(cache_dir, seg)
    if os.path.isfile(cache) and os.path.getsize(cache) > 44:
        return cache, True, 0

    for key in keys:
        for model in (TTS_MODEL, FALLBACK_MODEL):
            instructions = seg.get("style") if model == TTS_MODEL else None
            attempt = 0
            while attempt < 2:  # 审核误报最多重试一次
                attempt += 1
                try:
                    data, chars = _request(key, model, seg["text"], instructions)
                except Exception as exc:  # noqa: BLE001
                    kind = _classify(exc)
                    log.warning(
                        "tts: 段[%s] key=%s… model=%s 第%d次失败(%s): %s",
                        seg.get("kind"), key[:8], model, attempt, kind, exc,
                    )
                    if kind == "moderation":
                        if attempt == 1:
                            continue  # 误报重试一次
                        return None  # 文本固定，换 Key/模型无意义
                    if kind in ("quota", "auth"):
                        _note_key(key, False, kind)
                        break  # 换下一把 Key
                    break  # 网络/其他 → 换模型
                _note_key(key, True)
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache, "wb") as handle:
                    handle.write(data)
                return cache, False, chars
    log.error("tts: 段[%s] 所有 Key/模型尝试失败", seg.get("kind"))
    return None


def synthesize_segments(segments: list[dict], api_keys: list[str] | None, cache_dir: str) -> list[dict]:
    """合成五段旁白 → [{kind,text,start,window,path,cached}]。

    全部失败（且输入非空）抛 VoUnavailable；部分成功用部分——混音端按段
    摆放，缺段只少一句话。
    """

    os.makedirs(cache_dir, exist_ok=True)
    keys = [k for k in (api_keys or []) if k]
    out: list[dict] = []
    billed = 0
    cached_count = 0
    for seg in segments:
        result = None
        if keys:
            result = _synthesize_segment(seg, keys, cache_dir)
        else:
            log.warning("tts: 无可用 API Key，段[%s] 跳过", seg.get("kind"))
        if result is None:
            continue
        path, cached, chars = result
        billed += chars
        cached_count += 1 if cached else 0
        out.append({**seg, "path": path, "cached": cached})
    log.info(
        "tts: 旁白 %d/%d 段就绪（缓存命中 %d，本次计费 %d 字符）",
        len(out), len(segments), cached_count, billed,
    )
    if segments and not out:
        raise VoUnavailable("TTS 全部片段合成失败（详见后端日志）")
    return out
