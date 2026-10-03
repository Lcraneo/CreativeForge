"""audio — 发布片音轨混音：CC0 音效按节拍排布 + 旁白音轨闪避（ducking）。

纯 numpy 实现，无随机数——同输入永远同字节（逐帧渲染管线的确定性纪律）。
输出 48kHz 立体声 16bit PCM `sfx.wav`，渲染端经 render.py --sfx 混入成片。

音频分层：
  * SFX 层——adapters/onetake/sfx_samples/ 的 CC0 采样（Kenney，接口音效）
    + 两个 numpy 自合成材质（whoosh 气声过渡 / sub 低频重音，interface 包
    没有这两类），按 timeline 节拍排布；
  * VO 层——tts.py 产出的旁白 wav（缓存文件路径传入），按段起点摆放；
    旁白活跃窗内 SFX 层整体压到 DUCK_GAIN（120ms 入 / 300ms 出）。
混后峰值规到 -8 dBFS（上游规则：给外部 BGM 预留空间）+ 软限幅。
"""

from __future__ import annotations

import logging
import math
import os
import struct
import subprocess
import wave

import numpy as np

log = logging.getLogger("studio.showcase")

SR = 48000
PEAK_TARGET = 0.398  # -8 dBFS
DUCK_GAIN = 0.35
DUCK_IN_S = 0.12
DUCK_OUT_S = 0.30

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sfx_samples")

# 自合成材质名（与 sfx_samples/ 的文件名共用一张放置表）
WHOOSH = "WHOOSH"
SUB = "SUB"

# 解码缓存：进程内一次解码，全任务复用（同一批采样反复放置）
_DECODED: dict[str, np.ndarray] = {}


# ── 解码（ffmpeg 统一转 48k 单声道 f32；ogg/wav 通吃）────────────────────

def _ffmpeg() -> str | None:
    from adapters.onetake.render_client import _ff_binaries

    ffmpeg, _ = _ff_binaries()
    return ffmpeg


def load_sample(name: str) -> np.ndarray:
    """按名加载音效（sfx_samples/<name>.ogg 或自合成材质），48k mono f32。"""

    if name in _DECODED:
        return _DECODED[name]
    if name == WHOOSH:
        clip = _synth_whoosh()
    elif name == SUB:
        clip = _synth_sub()
    else:
        path = os.path.join(SAMPLES_DIR, "{}.ogg".format(name))
        if not os.path.isfile(path):
            raise FileNotFoundError("音效采样缺失：{}".format(path))
        clip = _decode_file(path)
    _DECODED[name] = clip
    return clip


def _decode_file(path: str, tempo: float = 1.0) -> np.ndarray:
    """ffmpeg 解码任意音频文件 → 48k 单声道 float32（tempo 变速用于旁白压窗）。"""

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg（static-ffmpeg/imageio-ffmpeg）")
    cmd = [ffmpeg, "-v", "error", "-i", path]
    if abs(tempo - 1.0) > 1e-3:
        factor = max(0.5, min(2.0, tempo))
        cmd += ["-filter:a", "atempo={:.4f}".format(factor)]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("音频解码失败：{} ({})".format(path, proc.stderr[-160:].decode("utf-8", "replace")))
    samples = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32)
    return samples


# ── 自合成材质（确定性，无随机数）────────────────────────────────────────

def _synth_whoosh(dur: float = 0.55, f0: float = 300.0, f1: float = 2600.0) -> np.ndarray:
    """气声过渡：噪声经随时间移动的 FFT 带通 + 不对称包络（模拟 onetake air）。"""

    n = int(SR * dur)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    rng = np.random.default_rng(7)  # 固定种子：确定性
    noise = rng.standard_normal(n).astype(np.float32)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    # 通带中心 f0→f1 对数滑移，宽度 0.6 倍频程；分 12 段近似时变滤波
    out = np.zeros(n, dtype=np.float32)
    seg = n // 12
    for i in range(12):
        center = f0 * (f1 / f0) ** (i / 11.0)
        lo, hi = center / 1.5, center * 1.5
        band = spectrum.copy()
        band[(freqs < lo) | (freqs > hi)] = 0
        piece = np.fft.irfft(band, n)[:seg] if i < 11 else np.fft.irfft(band, n)[seg * 11:]
        out[i * seg : i * seg + len(piece)] = piece
    envelope = np.clip(np.sin(np.pi * np.clip(t, 0, 1)), 0.0, None) ** 1.4
    envelope *= np.where(t < 0.4, t / 0.4, 1.0)
    out *= envelope
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak).astype(np.float32)


def _synth_sub(f: float = 62.0, dur: float = 0.65) -> np.ndarray:
    """低频重音：正弦 + 指数降音高 + 软饱和（模拟 onetake sub 的"砸地"感）。"""

    n = int(SR * dur)
    t = np.arange(n, dtype=np.float32) / SR
    freq = f * (1.0 + 2.2 * np.exp(-t * 28.0))
    phase = np.cumsum(2.0 * math.pi * freq / SR).astype(np.float32)
    out = np.sin(phase) * np.exp(-t * 5.5)
    out = np.tanh(out * 1.8) / math.tanh(1.8)
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak).astype(np.float32)


# ── 放置与混音 ────────────────────────────────────────────────────────────

def _placements(cf: dict) -> list[tuple[float, str, float]]:
    """节拍 → 音效放置表 (t, material, gain)。拍名与 timeline_mapper 对齐。"""

    beats = dict(cf.get("beats") or {})
    cuts = [float(t) for t in (cf.get("cuts") or [])]

    def at(name: str, default: float) -> float:
        return float(beats.get(name, default))

    plan = [
        (at("hookIn", 0.12), "reveal_glass_02", 0.40),
        (at("artIn", 1.30), "reveal_glass_01", 0.55),
        (at("sweep", 3.45), WHOOSH, 0.42),
        (at("morphAnim0", 5.20), WHOOSH, 0.46),
        (at("strike", 7.55), SUB, 0.68),
        (at("strike", 7.55) + 0.03, "click_01", 0.38),
        (at("morphEngine0", 9.20), WHOOSH, 0.40),
        (at("engineHold0", 11.00), "maximize_01", 0.38),
    ]
    # 片尾 staccato 三连击：click/tick 交替
    clickers = ("click_02", "tick_01", "click_01")
    for index, t in enumerate(cuts):
        plan.append((t, clickers[index % len(clickers)], 0.52))
    # 收尾封印（end card wordmark 落定前 0.19s）
    plan.append((at("end", 13.20) - 0.19, "confirm_01", 0.48))
    return plan


def _place(master: np.ndarray, clip: np.ndarray, t: float, gain: float, pan: float = 0.0) -> None:
    """单声道 clip 摆进立体声 master（恒功率声像）。原地写。"""

    start = int(t * SR)
    if start >= len(master[0]) or start < 0:
        return
    end = min(len(master[0]), start + len(clip))
    piece = clip[: end - start] * gain
    gl = math.cos((pan + 1.0) * math.pi / 4.0)
    gr = math.sin((pan + 1.0) * math.pi / 4.0)
    master[0, start:end] += piece * gl
    master[1, start:end] += piece * gr


def _duck_envelope(length: int, vo_windows: list[tuple[float, float]]) -> np.ndarray:
    """SFX 层闪避包络：旁白窗内压到 DUCK_GAIN，120ms 入 / 300ms 出。"""

    env = np.ones(length, dtype=np.float32)
    for t0, t1 in vo_windows:
        i0 = max(0, int(t0 * SR))
        i1 = min(length, int(t1 * SR))
        if i1 <= i0:
            continue
        env[i0:i1] = DUCK_GAIN
        rin = max(1, int(DUCK_IN_S * SR))
        rout = max(1, int(DUCK_OUT_S * SR))
        lead0, lead1 = max(0, i0 - rin), i0
        env[lead0:lead1] = np.linspace(1.0, DUCK_GAIN, lead1 - lead0, dtype=np.float32)
        tail0, tail1 = i1, min(length, i1 + rout)
        env[tail0:tail1] = np.linspace(DUCK_GAIN, 1.0, tail1 - tail0, dtype=np.float32)
    return env


def build_sfx_track(job_dir: str, cf: dict, vo_segments: list[dict] | None = None) -> str:
    """合成整条音轨并写 job_dir/sfx.wav。→ 文件绝对路径。

    vo_segments: tts.synthesize_segments 的产物（含 path/start/window）；
    None 或空列表时输出纯音效版（TTS 降级路径）。
    """

    duration = float((cf.get("meta") or {}).get("dur") or 15.0)
    length = int(duration * SR) + SR  # 尾部 1s 余量，-shortest 由渲染端裁
    master = np.zeros((2, length), dtype=np.float32)
    sfx = np.zeros((2, length), dtype=np.float32)

    placed = []
    for t, material, gain in _placements(cf):
        try:
            clip = load_sample(material)
        except Exception as exc:  # noqa: BLE001 - 单个采样缺失不拖垮整条音轨
            log.warning("audio: 采样 %s 加载失败：%s", material, exc)
            continue
        _place(sfx, clip, t, gain)
        placed.append(material)

    vo_windows: list[tuple[float, float]] = []
    vo_count = 0
    for seg in vo_segments or []:
        try:
            window = float(seg.get("window") or 2.0)
            clip = _decode_file(seg["path"])
            real = len(clip) / SR
            tempo = 1.0
            if real > window - 0.05:
                tempo = min(1.3, real / max(0.5, window - 0.1))
                clip = _decode_file(seg["path"], tempo=tempo)
            _place(master, clip, float(seg.get("start") or 0.0), 0.92)
            vo_windows.append((float(seg.get("start") or 0.0), float(seg.get("start") or 0.0) + len(clip) / SR))
            vo_count += 1
            if tempo > 1.01:
                log.info("audio: 旁白段 %s 时长 %.2fs 超窗 %.2fs，atempo %.3f 压回", seg.get("kind"), real, window, tempo)
        except Exception as exc:  # noqa: BLE001 - 单段旁白失败不拖垮整条音轨
            log.warning("audio: 旁白段 %s 摆放失败：%s", seg.get("kind"), exc)

    # 旁白窗内闪避 SFX 层，再并入主轨
    if vo_windows:
        sfx *= _duck_envelope(length, vo_windows)
    master += sfx

    peak = float(np.abs(master).max())
    if peak > 0:
        master = np.tanh(master * 1.2) / math.tanh(1.2)  # 先软限幅防削波
        peak = float(np.abs(master).max())
        master *= PEAK_TARGET / peak  # 再规到 -8dBFS（上游规则）

    out_path = os.path.join(job_dir, "sfx.wav")
    pcm = (np.clip(master.T, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(out_path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())
    log.info(
        "audio: sfx.wav 完成 %.2fs | 音效 %d 处 | 旁白 %d 段%s",
        duration,
        len(placed),
        vo_count,
        "" if vo_count else "（纯音效降级版）",
    )
    return out_path
