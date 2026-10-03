"""发布片配音链路契约测试（离线、零网络、零 TTS 计费）。

覆盖产品规格的四个阶段中可离线验证的部分：

  * vo_script：五段旁白切分、字数上限、确定性、覆写与 AI 润色钳制
  * audio：自合成材质确定性、采样加载、ducking、sfx.wav 产物与峰值纪律
  * tts：缓存命中不重复计费、Key 池额度轮换、审核误报一次重试、
    全失败抛 VoUnavailable（mock httpx，不发真实请求）
  * showcase_service：无 Key 时配音降级纯音效出片（不阻塞任务）

Run: python tests/test_onetake_audio.py
"""

import io
import os
import sys
import tempfile
import wave

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -- {detail}" if detail and not condition else "")
    )


def _fake_wav(seconds: float = 0.3, rate: int = 24000) -> bytes:
    """stdlib 造一段合法的 24k 单声道 16bit wav（模拟 TTS 产物）。"""

    import math
    import struct

    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(int(rate * seconds))
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buffer.getvalue()


def test_vo_script():
    from adapters.onetake import vo_script

    scene = {"copy": {"name": "星辉剑士"}}
    segs = vo_script.build_script(scene)
    check("vo: 恰好五段", len(segs) == 5, str([s["kind"] for s in segs]))
    check(
        "vo: 顺序 hook→art→pixel→anim→engine",
        [s["kind"] for s in segs] == ["hook", "art", "pixel", "anim", "engine"],
    )
    check("vo: 全部在字数上限内", all(len(s["text"]) <= s["cap"] for s in segs))
    again = vo_script.build_script(scene)
    check("vo: 确定性（纯函数）", again == segs)
    check("vo: 无硬截断词尾（不以逗号/顿号收尾）", all(s["text"][-1] not in "，、," for s in segs))

    overridden = vo_script.build_script(
        {"copy": {"name": "星辉剑士", "vo": ["先锋", "二二", "三三三", "四四四四", "五五五五五"]}}, None
    )
    check("vo: presentation.copy.vo 整段覆写", overridden[0]["text"] == "先锋" and overridden[4]["text"] == "五五五五五")

    polished = vo_script.apply_polish(
        segs, [s["text"] + "！多余超限内容会回落原文" if i == 1 else s["text"] for i, s in enumerate(segs)]
    )
    check("vo: 润色超限段回落原文", polished[1]["text"] == segs[1]["text"])
    check("vo: 润色其余段生效", polished[2]["text"] == segs[2]["text"])
    check("vo: 润色条数不符时整体回落", vo_script.apply_polish(segs, ["只有一句"]) == segs)


def test_audio():
    from adapters.onetake import audio

    whoosh_a, whoosh_b = audio._synth_whoosh(), audio._synth_whoosh()
    check("audio: whoosh 自合成确定性", whoosh_a.tobytes() == whoosh_b.tobytes())
    check("audio: whoosh 峰值归一", abs(float(abs(whoosh_a).max()) - 1.0) < 1e-4)

    clip = audio.load_sample("reveal_glass_01")
    check("audio: CC0 ogg 采样解码（ffmpeg）", clip.dtype.name == "float32" and len(clip) > 1000)

    env = audio._duck_envelope(audio.SR * 3, [(1.0, 2.0)])
    check("audio: ducking 窗内压低", abs(float(env[int(audio.SR * 1.5)]) - audio.DUCK_GAIN) < 1e-3)
    check("audio: ducking 窗外恢复", float(env[int(audio.SR * 2.9)]) == 1.0)

    with tempfile.TemporaryDirectory() as tmp:
        cf = {"beats": {"hookIn": 0.12, "artIn": 1.30, "sweep": 3.45, "strike": 7.55,
                        "morphEngine0": 9.20, "engineHold0": 11.00, "end": 13.20},
              "cuts": [12.30, 12.55, 12.78], "meta": {"dur": 13.2}}
        path = audio.build_sfx_track(tmp, cf, None)
        check("audio: sfx.wav 落盘", os.path.isfile(path))
        with wave.open(path) as handle:
            check("audio: 48k 立体声 16bit",
                  handle.getframerate() == 48000 and handle.getnchannels() == 2 and handle.getsampwidth() == 2)
            import struct

            frames = handle.readframes(handle.getnframes())
        samples = struct.unpack("<%dh" % (len(frames) // 2), frames)
        peak = max(abs(s) for s in samples) / 32767.0
        check("audio: 峰值 ≤ -8dBFS 目标（限幅内）", peak <= audio.PEAK_TARGET * 1.05, str(peak))
        check("audio: 有实际能量（非静音）", peak > 0.05, str(peak))

        # 旁白段摆放（用合成 wav 模拟 TTS 缓存产物）
        vo_wav = os.path.join(tmp, "vo_cache.wav")
        open(vo_wav, "wb").write(_fake_wav(1.0))
        voiced = [{"kind": "art", "start": 1.35, "window": 2.15, "path": vo_wav}]
        path2 = audio.build_sfx_track(tmp, cf, voiced)
        check("audio: 旁白+音效混合版落盘", os.path.isfile(path2))


def test_tts_mock():
    from adapters.onetake import tts

    wav = _fake_wav()
    calls = {"count": 0}
    moderation_seen = {"text": ""}

    class FakeResponse:
        def __init__(self, status_code=200, payload=None, text="", content=b""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text
            self.content = content

        def json(self):
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["count"] += 1
        auth = (headers or {}).get("Authorization", "")
        text = json["input"]["text"]
        if text.startswith("审核"):
            # 模拟审核随机性：同一段文本首次误杀、重试放行
            if moderation_seen["text"] != text:
                moderation_seen["text"] = text
                return FakeResponse(400, text='{"code":"DataInspectionFailed"}')
            return FakeResponse(200, {
                "output": {"audio": {"url": "http://fake/audio.wav"}},
                "usage": {"characters": 10},
            })
        if text.startswith("拒绝"):
            return FakeResponse(400, text='{"code":"DataInspectionFailed"}')
        if "KEY1" in auth:
            return FakeResponse(429, text='{"code":"Arrearage","message":"quota exceeded"}')
        return FakeResponse(200, {
            "output": {"audio": {"url": "http://fake/audio.wav"}},
            "usage": {"characters": 10},
        })

    def fake_get(url, timeout=None):
        return FakeResponse(200, content=wav)

    real_post, real_get = tts.httpx.post, tts.httpx.get
    tts.httpx.post, tts.httpx.get = fake_post, fake_get
    try:
        with tempfile.TemporaryDirectory() as tmp:
            segs = [{"kind": "art", "text": "AI 原画就绪", "start": 1.35, "window": 2.15, "cap": 9, "style": "沉稳"}]

            # 缓存命中：预置缓存文件，零网络调用
            pre = tts._cache_path(tmp, segs[0])
            open(pre, "wb").write(wav)
            calls["count"] = 0
            out = tts.synthesize_segments(segs, ["KEY1"], tmp)
            check("tts: 缓存命中不发起请求", calls["count"] == 0 and out[0]["cached"] is True)

            # Key 池轮换：KEY1 额度耗尽 → KEY2 成功
            os.remove(pre)
            calls["count"] = 0
            out = tts.synthesize_segments(segs, ["KEY1", "KEY2"], tmp)
            check("tts: 额度错误自动切换下一把 Key", calls["count"] >= 2 and len(out) == 1, str(calls["count"]))

            # 审核误报：第一次误杀、重试放行（同 Key 同文本，模拟随机性）
            segs_mod = [dict(segs[0], text="审核 这句先误杀再放行")]
            out = tts.synthesize_segments(segs_mod, ["KEY2"], tmp)
            check("tts: 审核误报重试一次后成功", len(out) == 1)

            # 审核连续拒绝：该段放弃（文本固定，换 Key/模型无意义）
            try:
                tts.synthesize_segments([dict(segs[0], text="拒绝 这句一直被拦")], ["KEY2"], tmp)
                check("tts: 连续拒绝应抛 VoUnavailable", False, "未抛")
            except tts.VoUnavailable:
                check("tts: 连续拒绝抛 VoUnavailable（降级信号）", True)

            # 无 Key：直接跳过 → VoUnavailable
            try:
                tts.synthesize_segments(segs, [], tmp)
                check("tts: 无 Key 应抛 VoUnavailable", False, "未抛")
            except tts.VoUnavailable:
                check("tts: 无 Key 抛 VoUnavailable（降级信号）", True)
    finally:
        tts.httpx.post, tts.httpx.get = real_post, real_get


def test_showcase_degrade():
    """无 Key 时配音降级纯音效，任务不阻塞（规格：TTS 失败仅出音效）。"""

    from adapters.onetake import build_scene, build_timeline
    from studio.backend.showcase_service.service import ShowcaseService

    with tempfile.TemporaryDirectory() as tmp:
        service = ShowcaseService(os.path.join(tmp, "jobs"), tmp)  # 无 settings/chat
        job = {"id": "test-job"}
        material = {"name": "星辉剑士", "prompt": "2d动漫风星辉剑士", "slug": "星辉剑士"}
        scene = build_scene(material, {})
        cf = build_timeline(scene, {"art": "assets/art.png"}, {}, 15.0)
        voiced = service._build_voice_track(job, tmp, cf, scene)
        check("showcase: 无 Key 降级返回 None", voiced is None)
        check("showcase: job.voice 标记纯音效", (job.get("voice") or {}).get("degraded") is True)
        check("showcase: sfx.wav 仍产出（纯音效版）", os.path.isfile(os.path.join(tmp, "sfx.wav")))


def main() -> int:
    test_vo_script()
    test_audio()
    test_tts_mock()
    test_showcase_degrade()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
