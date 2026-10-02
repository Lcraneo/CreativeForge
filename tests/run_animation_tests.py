"""Animation system verification (no GPU / no network).

    * PNG decode <-> encode round trip
    * animated GIF encoder (GIF89a, dimensions, loop extension)
    * pose frames differ across phases; sprite sheet packing
    * style recognition + character extraction
    * consistency similarity (identical -> ~1.0)
    * full pipeline: fps x duration -> frame count, gif/sheet output

Run: python tests/run_animation_tests.py
"""

import os
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from artgen import (  # noqa: E402
    STYLE_LABELS,
    create_animation,
    decode_png,
    encode_gif,
    encode_rgba,
    render_character_view,
)
from artgen.anim import pack_sheet, render_action_frames  # noqa: E402
from artgen.style import (  # noqa: E402
    analyze_rgba,
    dominant_palette,
    extract_character,
    similarity_rgba,
)

CHECKS = []
ROLES = {
    "outline": "#1f2a44",
    "base": "#4aa3e0",
    "accent": "#ffd166",
    "hair": "#2b6cb0",
    "skin": "#ffe9d6",
    "eyes": "#2b2b2b",
    "metal": "#cfd8e3",
}


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -- {detail}" if detail and not condition else "")
    )


def main() -> int:
    params = {"palette": ROLES, "seed": 7}

    # -- PNG round trip --------------------------------------------------
    png = render_character_view(params, "front", 256)
    width, height, rgba = decode_png(png)
    check(
        "png decodes to 256x256 RGBA",
        width == 256 and height == 256 and len(rgba) == width * height * 4,
    )
    reencoded = encode_rgba(width, height, rgba)
    check("png re-encode is valid", reencoded[:8] == b"\x89PNG\r\n\x1a\n")

    # -- style + character analysis -------------------------------------
    profile = analyze_rgba(width, height, rgba)
    check("style label known", profile["style"] in STYLE_LABELS, profile["style"])
    check(
        "clean cel art recognised as 2d",
        profile["style"] in ("2d_cel", "2d_semi"),
        profile["style"],
    )
    check("confidence in range", 0.0 <= profile["confidence"] <= 1.0)
    char = extract_character(width, height, rgba)
    bx0, by0, bx1, by1 = char["bbox"]
    check(
        "character bbox within bounds",
        0 <= bx0 < bx1 <= width and 0 <= by0 < by1 <= height,
        str(char["bbox"]),
    )
    palette = dominant_palette(width, height, rgba, count=6)
    check(
        "dominant palette hex",
        bool(palette) and all(p.startswith("#") and len(p) == 7 for p in palette),
    )

    # -- frames ----------------------------------------------------------
    frames = render_action_frames(params, "walk", 8, 192)
    check("8 frames rendered at 192", len(frames) == 8 and frames[0][0] == 192)
    check("frames differ across phase", frames[0][2] != frames[4][2])
    sheet_w, sheet_h, sheet_rgba = pack_sheet(frames)
    check("sheet packed horizontally", sheet_w == 192 * 8 and sheet_h == 192)

    # -- GIF -------------------------------------------------------------
    gif = encode_gif([f[2] for f in frames], 192, 192, fps=12, loop=0)
    check("gif86a header", gif[:6] == b"GIF89a")
    gw, gh = struct.unpack("<HH", gif[6:10])
    check("gif dimensions", gw == 192 and gh == 192)
    check("gif has netscape loop", b"NETSCAPE2.0" in gif)
    check("gif terminates", gif[-1:] == b"\x3b")

    # -- consistency -----------------------------------------------------
    same = similarity_rgba((width, height, rgba), (width, height, rgba))
    check("identical similarity high", same["overall"] >= 0.95, str(same))
    other = render_character_view(
        {"palette": ["#111111", "#330000", "#ff0000", "#00ff00", "#0000ff"], "seed": 999},
        "front",
        256,
    )
    ow, oh, orx = decode_png(other)
    diff = similarity_rgba((width, height, rgba), (ow, oh, orx))
    check(
        "different source lowers palette sim",
        diff["palette"] < same["palette"],
        f"{diff['palette']} vs {same['palette']}",
    )

    # -- full pipeline ---------------------------------------------------
    result = create_animation(params=params, action="attack", fps=10, duration=1.5, size=192)
    check("frame count = fps*duration", result["frame_count"] == 15, str(result["frame_count"]))
    check("fps/duration echoed", result["fps"] == 10 and abs(result["duration"] - 1.5) < 1e-6)
    check("gif produced", result["gif"][:6] == b"GIF89a")
    check("sheet produced", result["sheet"][:8] == b"\x89PNG\r\n\x1a\n")
    check("animation frames exported", len(result["frames"]) == result["frame_count"])
    check(
        "consistency computed",
        0.0 <= result["consistency"]["overall"] <= 1.0 and "passed" in result["consistency"],
    )
    check(
        "style matched (self anchor)",
        result["consistency"]["palette"] >= 0.9,
        str(result["consistency"]),
    )

    # reference from an uploaded PNG -> measured against it
    upload = create_animation(
        params=params, action="idle", fps=8, duration=1.0, size=160, reference=png
    )
    check(
        "upload reference accepted",
        upload["frame_count"] == 8 and upload["consistency"]["frames_checked"] >= 1,
    )

    # -- source-driven animation (content/style/composition preserved) ----
    driven = create_animation(
        params=None, action="walk", fps=10, duration=1.0, size=256, source_bytes=png
    )
    check(
        "source-driven consistency high",
        driven["consistency"]["overall"] >= 0.9,
        str(driven["consistency"]),
    )
    check(
        "source-driven frames animate",
        driven["frames"][0] != driven["frames"][driven["frame_count"] // 2],
    )
    check("source-driven gif", driven["gif"][:6] == b"GIF89a")
    check("source-driven reference is the source", driven["style"]["palette_size"] > 0)

    # -- studio asset resolution falls back to persistent history ---------
    from studio.backend.api.routes import _resolve_asset

    class _Assets:
        def get(self, asset_id):
            return None

        def latest(self):
            return None

    class _History:
        def get(self, record_id):
            return {"asset": {"id": "ast1"}} if record_id == "ast1" else None

        def list(self, limit=100):
            return [{"asset": {"id": "ast1"}}]

    class _Runtime:
        assets = _Assets()
        history = _History()

    check(
        "asset resolved from history by id",
        (_resolve_asset(_Runtime(), "ast1") or {}).get("id") == "ast1",
    )
    check(
        "asset resolved from latest history",
        (_resolve_asset(_Runtime(), None) or {}).get("id") == "ast1",
    )
    check("unknown asset stays None", _resolve_asset(_Runtime(), "nope") is None)

    # ── AI 视频驱动产物回归（防"生成的动画无法播放"类退化）──────────────
    # 全离线：合成 mp4（前 10 帧静止模拟 i2v 开头，之后方块平移起伏模拟
    # 角色动作）→ _slice_video 抽帧 → compose_animation → GIF 结构校验。
    try:
        import imageio.v2 as _probe  # noqa: F401

        import numpy as _np  # noqa: F401

        HAS_FFMPEG = True
    except Exception:
        HAS_FFMPEG = False

    if not HAS_FFMPEG:
        check("imageio/ffmpeg available for video regression", False, "install imageio + imageio-ffmpeg")
    else:
        import io as _io
        import os as _os
        import tempfile as _tempfile

        from PIL import Image as _PILImage, ImageSequence as _PILImageSeq

        from studio.backend.animation_service.service import AnimationService

        service = AnimationService(_os.path.join(_tempfile.gettempdir(), "cf_anim_test"))

        def _write_synth_mp4(path, total=96, side=192):
            import imageio.v2 as _imageio

            writer = _imageio.get_writer(path, fps=24)
            for i in range(total):
                frame = _np.full((side, side, 3), 235, dtype=_np.uint8)
                t = max(0, i - 10) / max(1, total - 10)
                x = int(40 + t * (side - 110))
                y = int(side * 0.45 + (18 if (i // 6) % 2 == 0 else -18))
                frame[y : y + 60, x : x + 60] = (40, 60, 120)
                writer.append_data(frame)
            writer.close()

        synth_mp4 = _os.path.join(_tempfile.gettempdir(), "cf_synth_i2v.mp4")
        _write_synth_mp4(synth_mp4)
        with open(synth_mp4, "rb") as handle:
            synth_bytes = handle.read()

        frames = service._slice_video(synth_bytes, b"", fps=12, duration=1.0, size=192, min_count=20)
        check("slice_video samples >= 20 frames", len(frames) >= 20, f"got {len(frames)}")
        check("slice_video frames sized to canvas", all(w == 192 and h == 192 for w, h, _ in frames))
        check(
            "slice_video keeps visible motion (subject moves between frames)",
            any(
                sum(
                    abs(a - b)
                    for a, b in zip(
                        _PILImage.frombytes("RGBA", (w, h), bytes(rgba)).convert("L").resize((24, 24)).tobytes(),
                        _PILImage.frombytes("RGBA", (w, h), bytes(frames[i + 1][2])).convert("L").resize((24, 24)).tobytes(),
                    )
                )
                > 1000
                for i, (w, h, rgba) in enumerate(frames[:-1])
            ),
        )

        from artgen import compose_animation

        composed = compose_animation(frames_rgba=frames, fps=12, size=192)
        check("composed gif non-empty", len(composed["gif"]) > 1000, f"{len(composed['gif'])} bytes")

        gif_img = _PILImage.open(_io.BytesIO(composed["gif"]))
        gif_frames = sum(1 for _ in _PILImageSeq.Iterator(gif_img))
        check("gif decodable with expected frame count", gif_frames == len(frames), f"{gif_frames} vs {len(frames)}")
        check("gif size matches canvas", gif_img.size == (192, 192))

    # ── 模型调用错误分类（审核/额度/鉴权/网络，全离线）───────────────────
    import httpx as _httpx

    from studio.backend.model_service.service import (
        _soften_prompt,
        classify_error,
        describe_error,
    )

    def _http_exc(status, body):
        request = _httpx.Request("POST", "https://dashscope.example.com/api")
        response = _httpx.Response(status, request=request, text=body)
        return _httpx.HTTPStatusError("err", request=request, response=response)

    check("classify quota: arrearage body", classify_error(_http_exc(400, '{"code":"Arrearage"}')) == "quota")
    check("classify quota: 429 status", classify_error(_http_exc(429, "")) == "quota")
    check("classify auth: invalid key", classify_error(_http_exc(401, '{"code":"InvalidApiKey"}')) == "auth")
    check(
        "classify moderation: DataInspectionFailed",
        classify_error(_http_exc(400, '{"code":"DataInspectionFailed","message":"content check"}')) == "moderation",
    )
    check(
        "classify moderation: IP infringement",
        classify_error(_http_exc(400, '{"code":"IPInfringementSuspect"}')) == "moderation",
    )
    check("classify network: connect timeout", classify_error(_httpx.ConnectTimeout("timed out")) == "network")
    check("classify network: 502", classify_error(_http_exc(502, "bad gateway")) == "network")
    check("classify fatal: model not exist", classify_error(_http_exc(400, '{"code":"Model.NotFound"}')) == "fatal")
    check(
        "describe moderation hides raw body",
        "审核" in describe_error(_http_exc(400, '{"code":"DataInspectionFailed"}'))
        and "{" not in describe_error(_http_exc(400, '{"code":"DataInspectionFailed"}')),
    )
    softened = _soften_prompt("The character attacks with a sword strike, then settles back.")
    check(
        "soften prompt neutralizes risky words",
        "attack" not in softened.lower() and "sword" not in softened.lower() and "strike" not in softened.lower(),
        softened,
    )
    check("soften prompt keeps original text when clean", _soften_prompt("walk in place") != "" and "attack" not in _soften_prompt("walk in place"))

    # ── 动作描述 AI 增强：门控 / 失败回退 / 持久缓存命中 ─────────────────
    import tempfile as _tempfile2

    from studio.backend.animation_service import service as _anim_service

    check(
        "motion enhance: switch off returns base",
        _anim_service.ai_enhance_motion_prompt(
            {"enabled": True, "api_key": "k", "chat_model": "m", "video_ai_enhance": False},
            "walk",
            "base prompt",
        )
        == "base prompt",
    )
    check(
        "motion enhance: unconfigured returns base",
        _anim_service.ai_enhance_motion_prompt({}, "walk", "base prompt") == "base prompt",
    )

    _orig_cache_path = _anim_service._MOTION_PROMPT_CACHE_PATH
    _orig_cache_dict = dict(_anim_service._motion_prompt_cache)
    _orig_chat_provider = None
    try:
        import studio.backend.model_service.service as _msvc

        _anim_service._MOTION_PROMPT_CACHE_PATH = os.path.join(
            _tempfile2.gettempdir(), "cf_motion_cache_test.json"
        )
        _anim_service._motion_prompt_cache = {}
        _orig_chat_provider = _msvc.ChatProvider

        class _FakeChat:
            def __init__(self, settings):
                pass

            def chat(self, system, user, temperature=0.6):
                return {
                    "model": "fake",
                    "content": "The character walks with a lively bounce, shoulders swinging "
                    "in rhythm, heels touching the ground softly, cloth settling after each step.",
                }

        _enhance_settings = {
            "enabled": True,
            "api_key": "k",
            "chat_model": "m",
            "video_ai_enhance": True,
        }
        _msvc.ChatProvider = _FakeChat
        enhanced = _anim_service.ai_enhance_motion_prompt(_enhance_settings, "walk", "walk in place")
        check("motion enhance rewrites via chat", "bounce" in enhanced, enhanced[:80])

        def _boom(settings):
            raise AssertionError("cache should hit, chat must not be called again")

        _msvc.ChatProvider = _boom
        again = _anim_service.ai_enhance_motion_prompt(_enhance_settings, "walk", "walk in place")
        check("motion enhance cache hits on repeat", again == enhanced, again[:80])
    finally:
        _anim_service._MOTION_PROMPT_CACHE_PATH = _orig_cache_path
        _anim_service._motion_prompt_cache = _orig_cache_dict
        if _orig_chat_provider is not None:
            _msvc.ChatProvider = _orig_chat_provider
        try:
            _probe_path = os.path.join(_tempfile2.gettempdir(), "cf_motion_cache_test.json")
            if os.path.isfile(_probe_path):
                os.remove(_probe_path)
        except OSError:
            pass

    # ── 风格提示词模板库 ─────────────────────────────────────────────────
    from studio.backend.model_service.style_templates import STYLE_TEMPLATES

    check("style templates: at least 8", len(STYLE_TEMPLATES) >= 8, str(len(STYLE_TEMPLATES)))
    check(
        "style templates: clauses carry no marker chars",
        all("【" not in t["clause"] and "】" not in t["clause"] for t in STYLE_TEMPLATES.values()),
    )
    check(
        "style templates: labels unique",
        len({t["label"] for t in STYLE_TEMPLATES.values()}) == len(STYLE_TEMPLATES),
    )
    check(
        "style templates: every entry has clause+negative",
        all(t.get("clause") and t.get("negative") for t in STYLE_TEMPLATES.values()),
    )

    # ── 角色资产包一键导出（离线组装）────────────────────────────────────
    import shutil as _shutil
    import tempfile as _tempfile3
    import zipfile as _zipfile

    from studio.backend.export_service import character_package as _cpkg

    _pkg_dir = os.path.join(_tempfile3.gettempdir(), "cf_pkg_out_test")
    _pkg_anim_dir = os.path.join(_tempfile3.gettempdir(), "cf_pkg_anim_test")
    os.makedirs(_pkg_dir, exist_ok=True)
    os.makedirs(_pkg_anim_dir, exist_ok=True)
    try:
        from PIL import Image as _PkgImg

        _gif_fd, _gif_tmp = _tempfile3.mkstemp(suffix=".gif")
        os.close(_gif_fd)  # Windows：不关句柄 rename/remove 会报占用
        _PkgImg.new("RGBA", (4, 4), (10, 20, 30, 255)).save(_gif_tmp, "GIF")
        with open(_gif_tmp, "rb") as _handle:
            _gif_bytes = _handle.read()
        os.remove(_gif_tmp)
        with open(os.path.join(_pkg_anim_dir, "anim1.gif"), "wb") as _handle:
            _handle.write(_gif_bytes)

        _pkg_meta = {
            "id": "anim1",
            "asset_id": "astPkg",
            "requested_action": "walk",
            "source": "video",
            "urls": {"gif": "/api/animation/anim1.gif", "sheet": "/api/animation/anim1_sheet.png"},
            "frames": 12,
            "fps": 12,
            "created_at": 1.0,
        }
        _orig_pkg_anim = _cpkg._ANIMATION_DIR
        _cpkg._ANIMATION_DIR = _pkg_anim_dir
        try:
            _pkg_asset = {"id": "astPkg", "name": "测试角色", "type": "character"}
            _pkg_result = _cpkg.export_character_package(
                _pkg_asset, [_pkg_meta], _pkg_dir, engine="cocos"
            )
            check("character package: zip written", os.path.isfile(_pkg_result["path"]))
            with _zipfile.ZipFile(_pkg_result["path"]) as _zf:
                _names = _zf.namelist()
            check(
                "character package: manifest + readme inside",
                "manifest.json" in _names and "README.md" in _names,
            )
            check(
                "character package: animation gif packed",
                "animations/walk__ai-video.gif" in _names,
                str(_names),
            )
            check(
                "character package: missing views noted in manifest",
                "view_front" in _pkg_result["missing"],
                str(_pkg_result["missing"]),
            )
        finally:
            _cpkg._ANIMATION_DIR = _orig_pkg_anim
    finally:
        _shutil.rmtree(_pkg_dir, ignore_errors=True)
        _shutil.rmtree(_pkg_anim_dir, ignore_errors=True)

    # ── 额度仪表：本地估算台账 ───────────────────────────────────────────
    import tempfile as _tempfile4
    import time as _time

    from studio.backend.model_service import usage as _usage

    _orig_ledger_path = _usage._LEDGER_PATH
    _usage._LEDGER_PATH = os.path.join(_tempfile4.gettempdir(), "cf_usage_ledger_test.json")
    _usage._ledger = None  # 强制重载
    try:
        _now = _time.time()
        _usage.clear_usage()
        _usage.record_usage("image", "wanx2.1-t2i-turbo")
        _usage.record_usage("video", "wan2.2-i2v-plus")
        _usage.record_usage("chat", "qwen3-omni-flash")
        # 把最便宜的 chat 记录改成 40 天前：应落出 30 天统计窗口
        with open(_usage._LEDGER_PATH, "r", encoding="utf-8") as _handle:
            import json as _json2

            _rows = _json2.load(_handle)
        _rows[2]["at"] = _now - 40 * 86400
        with open(_usage._LEDGER_PATH, "w", encoding="utf-8") as _handle:
            _json2.dump(_rows, _handle)
        _usage._ledger = None  # 重载，模拟重启
        _summary = _usage.usage_summary()
        check(
            "usage: window keeps 2 of 3 calls (aged one excluded)",
            sum(b["calls"] for b in _summary["by_kind"]) == 2,
            str(_summary["by_kind"]),
        )
        check(
            "usage: today = image + video",
            abs(_summary["totals"]["today"] - (0.14 + 3.50)) < 0.01,
            str(_summary["totals"]),
        )
        check(
            "usage: video is costliest kind",
            _summary["by_kind"][0]["kind"] == "video" and _summary["by_kind"][0]["cost"] >= 3.5,
            str(_summary["by_kind"]),
        )
        check(
            "usage: ledger capped trim works",
            _usage.record_usage("chat", "m") or len(_usage._load()) == 4,
        )
        _usage.clear_usage()
        check("usage: clear empties ledger", _usage.usage_summary()["totals"]["today"] == 0.0)
    finally:
        _usage._LEDGER_PATH = _orig_ledger_path
        _usage._ledger = None
        try:
            os.remove(os.path.join(_tempfile4.gettempdir(), "cf_usage_ledger_test.json"))
        except OSError:
            pass

    # ── 复核补齐：生图调用 Key 池切换 + Key 健康状态 ─────────────────────
    _orig_ledger_path2 = _usage._LEDGER_PATH
    _usage._LEDGER_PATH = os.path.join(_tempfile4.gettempdir(), "cf_usage_ledger_test2.json")
    _usage._ledger = None
    _orig_dash = _msvc.ImageProvider._generate_dashscope
    try:
        _pool_calls = []

        def _fake_dash(self, prompt):
            _pool_calls.append(self.settings.get("api_key"))
            if len(_pool_calls) == 1:
                raise RuntimeError("HTTP 400: Arrearage")
            return {"file": None, "url": None, "model": "wanx-test"}

        _msvc.ImageProvider._generate_dashscope = _fake_dash
        _img_provider = _msvc.ImageProvider(
            {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "k-primary",
                "api_key_pool": ["k-backup"],
                "model": "wanx-test",
                "size": "1024x1024",
                "negative_prompt": "",
                "seed": "",
            }
        )
        _img_provider.generate("unique-prompt-{}".format(_time.time()))
        check(
            "image generation switches to backup key on quota error",
            _pool_calls == ["k-primary", "k-backup"],
            str(_pool_calls),
        )
        check(
            "key health recorded: primary quota, backup ok",
            _msvc._KEY_HEALTH.get("k-primary", {}).get("status") == "quota"
            and _msvc._KEY_HEALTH.get("k-backup", {}).get("status") == "ok",
        )
        _health = _msvc.key_health_view({"api_key": "k-primary", "api_key_pool": ["k-backup"]})
        check(
            "key health view: primary quota + pool ok",
            _health["primary"] == "quota" and _health["pool"] == ["ok"],
            str(_health),
        )

        _tmp_store_path = os.path.join(_tempfile4.gettempdir(), "cf_ms_test.json")
        _tmp_store = _msvc.ModelSettingsStore(_tmp_store_path)
        _pub = _tmp_store.update(
            {"api_key": "sk-test-primary-key-123", "api_key_pool_add": ["sk-test-backup-key-456"]}
        )
        check(
            "settings public exposes key_health",
            isinstance(_pub.get("key_health"), dict)
            and len(_pub["key_health"].get("pool") or []) == 1,
            str(_pub.get("key_health")),
        )
        os.remove(_tmp_store_path)
    finally:
        _msvc.ImageProvider._generate_dashscope = _orig_dash
        _usage._LEDGER_PATH = _orig_ledger_path2
        _usage._ledger = None
        try:
            os.remove(os.path.join(_tempfile4.gettempdir(), "cf_usage_ledger_test2.json"))
        except OSError:
            pass

    # ── 队列中心：资产批次 + 动作批次聚合 ────────────────────────────────
    import copy as _copy

    from studio.backend.api import routes as _routes
    from studio.backend.animation_service import service as _queue_anim

    class _QueueRuntime:
        def __init__(self):
            self.batches = {
                "b1": {
                    "id": "b1", "goal": "像素法师一批", "count": 2, "mode": "seed",
                    "status": "running", "created_at": 2.0,
                    "tasks": [{"task_id": "t1", "index": 1, "status": "success"}],
                }
            }

        def batch_snapshot(self, batch_id):
            return _copy.deepcopy(self.batches.get(batch_id))

    _queue_anim._ACTION_BATCHES.clear()
    _queue_anim._ACTION_BATCHES["a1"] = {
        "id": "a1", "asset_id": "astQ", "status": "running", "total": 3,
        # 用当前时间：批次有 1h TTL，伪造的旧时间戳会被 _prune_action_batches 正常清理
        "created_at": _time.time(),
        "tasks": [{"action": "walk", "status": "generating"}, {"action": "run", "status": "done"}],
    }
    try:
        _router = _routes.build_router(_QueueRuntime())
        _queue_endpoint = next(
            route.endpoint
            for route in _router.routes
            if getattr(route, "path", "") == "/api/queue/snapshot"
        )
        _snap = _queue_endpoint()
        check(
            "queue: running counts both stores",
            _snap["running"] == 2,
            str(_snap.get("running")),
        )
        check(
            "queue: asset batch aggregated with live task status",
            _snap["asset_batches"][0]["tasks"][0]["status"] == "success",
            str(_snap["asset_batches"])[:120],
        )
        check(
            "queue: action batch merged with kind tag",
            _snap["action_batches"][0]["kind"] == "actions"
            and _snap["asset_batches"][0]["kind"] == "assets",
        )
    finally:
        _queue_anim._ACTION_BATCHES.clear()

    # ── 动作序列质量：曲线连续性 + 生物力学 + 体型自适应 ─────────────────
    import math as _mq

    from artgen.anim import ACTIONS as _ALL_ACTIONS, _pose
    from artgen.riganim import _motion_scales
    from artgen.sidewalk import _foot_path

    # 1) 循环动作接缝 C0+C1：phase 0/1 处值与导数连续（卡顿/跳跃的根除标准）
    for _name, _key in (("bob", "bob"), ("knee_l", "knee_l"), ("arm", "arm")):
        def _curve(p, _key=_key):
            return _pose("walk", p, None)[_key]

        _eps = 1e-5
        _d0 = (_curve(_eps) - _curve(0.0)) / _eps
        _d1 = (_curve(1.0) - _curve(1.0 - _eps)) / _eps
        check(
            f"walk {_name}: C0 at loop seam",
            abs(_curve(0.0) - _curve(1.0)) < 1e-6,
            f"gap={abs(_curve(0.0) - _curve(1.0))}",
        )
        check(f"walk {_name}: C1 at loop seam", abs(_d0 - _d1) < 0.02, f"d0={_d0:.4f} d1={_d1:.4f}")

    # 2) 一次性动作分段边界 C0（旧版蓄力/落地处的硬切 = 成片跳帧）
    for _boundary in (0.3, 0.55, 0.8):
        _gap = abs(
            _pose("attack", _boundary - 1e-9)["lean"] - _pose("attack", _boundary + 1e-9)["lean"]
        )
        check(f"attack: C0 at {_boundary}", _gap < 0.5, f"lean gap={_gap}")
    for _boundary in (0.22, 0.72):
        _gap = abs(
            _pose("jump", _boundary - 1e-9)["jump"] - _pose("jump", _boundary + 1e-9)["jump"]
        )
        check(f"jump: C0 at {_boundary}", _gap < 0.5, f"jump gap={_gap}")
        for _key in ("squat", "arm", "leg"):
            _gap = abs(
                _pose("jump", _boundary - 1e-9)[_key] - _pose("jump", _boundary + 1e-9)[_key]
            )
            check(f"jump {_key}: C0 at {_boundary}", _gap < 0.05, f"gap={_gap}")

    # 3) 生物力学：膝只朝屈曲方向弯、支撑期微屈不锁死、屈曲峰落在摆动相
    # （脚离地）窗口内；肘恒为屈曲
    _worst_knee = -99.0
    _stance_ok = True
    _peak_i, _peak_val = 0, 0.0
    for _i in range(720):
        _p = _pose("walk", _i / 720.0, None)
        _kl = _p["knee_l"]
        _worst_knee = max(_worst_knee, _kl)
        if abs(_kl) > abs(_peak_val):
            _peak_i, _peak_val = _i, _kl
        if _p["lift"][0] <= 0.0 and abs(_kl) > 12.5:
            _stance_ok = False
    check("walk knee: never hyperextends (angle ≤ 0)", _worst_knee <= 1e-9, str(_worst_knee))
    check("walk knee: stance flexion subtle (≤12°)", _stance_ok)
    _peak_pose = _pose("walk", _peak_i / 720.0, None)
    check(
        "walk knee: peak flexion inside swing window (foot airborne)",
        _peak_pose["lift"][0] > 0.0 and abs(_peak_val) > 25.0,
        f"phase={_peak_i / 720.0:.3f} knee={_peak_val:.1f} lift={_peak_pose['lift'][0]}",
    )
    _worst_elbow = max(_pose("walk", _i / 720.0, None)["elbow_l"] for _i in range(720))
    check("walk elbow: flexion only (angle ≤ 0)", _worst_elbow <= 1e-9, str(_worst_elbow))

    # 4) 侧视步态：脚底相对身体水平速度在触地/离地点连续（消除打滑/顿挫）
    def _fx(ph):
        return _foot_path(ph % 1.0, 96.0, 34.0)[0]

    _eps = 1e-5
    _d_contact = (_fx(_eps) - _fx(0.0)) / _eps - (_fx(1.0) - _fx(1.0 - _eps)) / _eps
    _d_toeoff = (_fx(0.5 + _eps) - _fx(0.5)) / _eps - (_fx(0.5) - _fx(0.5 - _eps)) / _eps
    check("side gait foot: C1 at contact", abs(_d_contact) < 0.05, f"delta={_d_contact}")
    check("side gait foot: C1 at toe-off", abs(_d_toeoff) < 0.05, f"delta={_d_toeoff}")
    check(
        "side gait foot: C0 at toe-off",
        abs(_fx(0.5 - _eps) - _fx(0.5 + _eps)) < 1e-4,
    )

    # 5) 体型自适应：Q 版关节角收敛、弹跳增强；小个子位移收敛
    _normal = _motion_scales({"head_ratio": 0.6, "bbox": [0, 0, 384, 384]}, 384)
    _chibi = _motion_scales({"head_ratio": 0.95, "bbox": [0, 0, 384, 384]}, 384)
    _small = _motion_scales({"head_ratio": 0.6, "bbox": [0, 0, 384, 150]}, 384)
    check("motion scales: chibi limb angles converge", _chibi["limb"] < _normal["limb"])
    check("motion scales: chibi vertical bounce amplified", _chibi["bob"] > _normal["bob"])
    check(
        "motion scales: small character shrinks pixel offsets (floor 0.55)",
        _small["offset"] < _normal["offset"] and _small["offset"] >= 0.55,
    )

    # 6) 全动作渲染冒烟：五类动作新曲线可渲染且帧间有运动
    for _action in _ALL_ACTIONS:
        _frames4 = render_action_frames(params, _action, 4, 160)
        check(
            f"motion smoke: {_action} renders with visible motion",
            len(_frames4) == 4 and _frames4[0][2] != _frames4[3][2],
        )

    # ── 分体修复回归：封闭背景洞回收 + 手臂区域头部保护区 ────────────────
    import io as _io

    from artgen.riganim import _absorb_enclosed_background, animate_rigged
    from PIL import Image as _TImg, ImageDraw as _TDraw

    def _make_pocket_png():
        """白底 + 躯干/双腿灰块，两腿之间封出一条**封闭白底竖洞**（洪泛
        不可达 → 会被误判主体），底部脚块封口。"""
        img = _TImg.new("RGB", (96, 96), (250, 250, 250))
        draw = _TDraw.Draw(img)
        draw.rectangle((30, 20, 66, 52), fill=(120, 120, 128))  # 躯干
        draw.rectangle((30, 52, 44, 90), fill=(120, 120, 128))  # 左腿
        draw.rectangle((52, 52, 66, 90), fill=(120, 120, 128))  # 右腿
        draw.rectangle((28, 90, 68, 95), fill=(90, 90, 96))  # 脚块封底
        buffer = _io.BytesIO()
        img.save(buffer, "PNG")
        return buffer.getvalue()

    _pocket_frames, _, _, _ = animate_rigged(
        _make_pocket_png(), "walk", 6, 96, segment_mask=None, keep_background=False
    )
    # 不变量：洞必须作为**主体**消失。腿摆动扫过空隙是物理正确的，但被
    # 误判成主体的"背景色块"会以不透明近白色出现在画面里——逐帧检查
    # 不存在背景色 (≈250,250,250) 且不透明的像素（腿/躯干是灰色系，
    # 双三次旋转不会造出 ≥240 的近白）。
    _leak = 0
    for _w, _h, _rgba in _pocket_frames:
        _img = _TImg.frombytes("RGBA", (_w, _h), bytes(_rgba))
        for _y in range(_h):
            for _x in range(_w):
                _r, _g, _b, _a = _img.getpixel((_x, _y))
                if _a > 128 and _r >= 240 and _g >= 240 and _b >= 240:
                    _leak += 1
    check(
        "dismember fix R1: enclosed background pocket never renders as subject",
        _leak == 0,
        f"{_leak} background-colored opaque pixels leaked",
    )

    def _make_chibi_face_png():
        """Q 版测试图：大头（绿）+ 脸中部品红嘴带 + 两侧手臂矩形（灰）。
        手臂矩形横穿嘴带所在高度——无头部保护时摆臂会把嘴带"片"走。"""
        img = _TImg.new("RGB", (128, 128), (250, 250, 250))
        draw = _TDraw.Draw(img)
        draw.ellipse((14, 4, 114, 84), fill=(30, 160, 90))  # 大头
        draw.rectangle((40, 58, 88, 76), fill=(230, 40, 160))  # 嘴带（脸中下部）
        draw.rectangle((44, 76, 84, 100), fill=(90, 130, 170))  # 躯干（独特色，刚体参照）
        draw.rectangle((44, 100, 56, 124), fill=(100, 100, 108))  # 左腿
        draw.rectangle((72, 100, 84, 124), fill=(100, 100, 108))  # 右腿
        draw.rectangle((16, 60, 60, 120), fill=(140, 140, 148))  # 左臂（横穿嘴带高度）
        draw.rectangle((68, 60, 112, 120), fill=(140, 140, 148))  # 右臂
        buffer = _io.BytesIO()
        img.save(buffer, "PNG")
        return buffer.getvalue()

    def _fake_chibi_rig():
        head_h = 0.60
        return {
            "bbox": [14, 4, 114, 124],
            "size": [128, 128],
            "source_size": [128, 128],
            "transparent": False,
            "confidence": 0.9,
            "proportion": "chibi",
            "head_ratio": 0.95,
            "head_height": head_h,
            "source_hash": "chibi-face-test",
            "points": {
                "root": [64, 124],
                "head": [64, 20],
                "neck": [64, 80],
                "shoulder_l": [40, 68],
                "elbow_l": [38, 94],
                "hand_l": [38, 118],
                "shoulder_r": [88, 68],
                "elbow_r": [90, 94],
                "hand_r": [90, 118],
                "hip_l": [50, 100],
                "knee_l": [50, 112],
                "foot_l": [50, 124],
                "hip_r": [78, 100],
                "knee_r": [78, 112],
                "foot_r": [78, 124],
            },
        }

    _face_frames, _, _, _ = animate_rigged(
        _make_chibi_face_png(),
        "walk",
        8,
        128,
        rig=_fake_chibi_rig(),
        segment_mask=None,
        keep_background=False,
    )

    def _magenta_stats(frame):
        _w, _h, _rgba = frame
        _img = _TImg.frombytes("RGBA", (_w, _h), bytes(_rgba))
        _xs, _ys, _n = [], [], 0
        for _y in range(_h):
            for _x in range(_w):
                _r, _g, _b, _a = _img.getpixel((_x, _y))
                if _a > 128 and _r > 180 and _g < 120 and _b > 110:
                    _xs.append(_x)
                    _ys.append(_y)
                    _n += 1
        if not _xs:
            return None
        return {
            "cx": sum(_xs) / _n,
            "cy": sum(_ys) / _n,
            "width": max(_xs) - min(_xs),
            "count": _n,
        }

    def _torso_cx(frame):
        _w, _h, _rgba = frame
        _img = _TImg.frombytes("RGBA", (_w, _h), bytes(_rgba))
        _acc, _n = 0, 0
        for _y in range(_h):
            for _x in range(_w):
                _r, _g, _b, _a = _img.getpixel((_x, _y))
                if _a > 128 and abs(_r - 30) < 40 and abs(_g - 160) < 40 and abs(_b - 90) < 40:
                    _acc += _x
                    _n += 1
        return (_acc / _n) if _n else None

    _stats = [s for s in (_magenta_stats(f) for f in _face_frames) if s is not None]
    _torso_cxs = [_torso_cx(f) for f in _face_frames]
    # 不变量一（不撕裂）：嘴带宽度恒定——被左右手臂反向"片"走时宽度会被
    # 拉伸摆动；随躯干刚体运动时宽度不变。
    _widths = [s["width"] for s in _stats]
    _width_drift = (max(_widths) - min(_widths)) / max(1, _widths[0])
    # 不变量二（刚体跟随）：嘴带与头部绿圆同属 upper 区域，应同步平移，
    # 两者的 X 质心差恒定；若嘴带被手臂层带走则会相对头部振荡。
    # （头部绿圆是纯 upper 参照——躯干/腿/臂的矩形互相重叠，污染参照。）
    _rel = [
        s["cx"] - tc
        for s, tc in zip(_stats, _torso_cxs)
        if tc is not None
    ]
    _rel_dev = max((abs(v - _rel[0]) for v in _rel), default=0.0)
    check(
        "dismember fix R2: chibi face band not sheared (width drift < 15%)",
        len(_stats) >= 6 and _width_drift < 0.15,
        f"widths={_widths}",
    )
    check(
        "dismember fix R2: chibi face band tracks torso rigidly (dev < 3px)",
        len(_rel) >= 6 and _rel_dev < 3.0,
        f"rel_dev={_rel_dev:.2f}px",
    )
    check(
        "dismember fix R2: interior colored band survives pocket absorption",
        len(_stats) >= 6,
    )

    # ── 帧粘连修复（分区独占所有权）回归 ─────────────────────────────────
    # 症状（试玩区/工作台实测）：膝弯/肘屈时父段层里那份"肢端拷贝"按父段
    # 角刚体旋转、与子层（小腿/前臂）的弯角渲染同屏叠加——观感即"上一帧
    # 骨骼姿态残留 + 顶点裂变 + 拖影"；裆部立柱矩形到脚底，把未旋转的
    # 原姿态腿列盖在每一帧上。修复：父段裁到膝/肘（子层独占肢端）、立柱
    # 裁到膝且逐帧只贴"已绘制覆盖图"之外的洞。
    # 夹具探针摆放纪律（缺一即门禁失效）：
    #   * 小腿/前臂色带只落在**子层独占区**——小腿带 y>knee+10（新大腿层
    #     已裁到 knee+8）、前臂带 y<knee-22 且抬高到臂侧（新上臂层已裁到
    #     elbow+6）；旧代码里这些带同时落在父段矩形 → 双份渲染 → 计数膨胀；
    #   * 膝下两腿之间放橙色柱：旧立柱矩形到脚底会把它**不旋转**地盖回
    #     （立柱门控/裁剪后新代码不再渲染它）；
    #   * 用 run 动作标定——58° 膝弯让新旧拷贝的分离距离最大。
    def _make_two_segment_png():
        img = _TImg.new("RGB", (128, 128), (250, 250, 250))
        draw = _TDraw.Draw(img)
        draw.ellipse((48, 2, 80, 26), fill=(60, 60, 70))  # 头
        draw.rectangle((50, 24, 78, 60), fill=(90, 130, 170))  # 躯干
        draw.rectangle((28, 28, 48, 50), fill=(80, 80, 92))  # 左上臂
        draw.rectangle((80, 28, 100, 50), fill=(80, 80, 92))  # 右上臂
        draw.rectangle((18, 56, 32, 70), fill=(150, 80, 190))  # 左前臂+手（紫探针）
        draw.rectangle((96, 56, 110, 70), fill=(150, 80, 190))  # 右前臂+手（紫探针）
        draw.rectangle((40, 60, 52, 92), fill=(70, 170, 190))  # 左大腿
        draw.rectangle((76, 60, 88, 92), fill=(70, 170, 190))  # 右大腿
        draw.rectangle((36, 103, 48, 124), fill=(230, 120, 40))  # 左小腿+脚（橙探针）
        draw.rectangle((80, 103, 92, 124), fill=(230, 120, 40))  # 右小腿+脚（橙探针）
        draw.rectangle((56, 66, 72, 94), fill=(190, 210, 90))  # 裆柱探针（髋→膝）
        draw.rectangle((56, 100, 72, 122), fill=(230, 120, 40))  # 膝下两腿间橙柱
        buffer = _io.BytesIO()
        img.save(buffer, "PNG")
        return buffer.getvalue()

    def _fake_straight_rig():
        return {
            "bbox": [14, 2, 114, 126],
            "size": [128, 128],
            "source_size": [128, 128],
            "transparent": False,
            "confidence": 0.9,
            "proportion": "normal",
            "head_ratio": 0.28,
            "head_height": 0.28,
            "source_hash": "two-segment-test",
            "points": {
                "root": [64, 126],
                "head": [64, 14],
                "neck": [64, 26],
                "shoulder_l": [44, 30],
                "elbow_l": [34, 52],
                "hand_l": [30, 72],
                "shoulder_r": [84, 30],
                "elbow_r": [94, 52],
                "hand_r": [98, 72],
                "hip_l": [48, 62],
                "knee_l": [46, 93],
                "foot_l": [42, 126],
                "hip_r": [80, 62],
                "knee_r": [82, 93],
                "foot_r": [86, 126],
            },
        }

    def _band_counts(frames, matcher):
        counts = []
        for _w, _h, _rgba in frames:
            _img = _TImg.frombytes("RGBA", (_w, _h), bytes(_rgba))
            _n = 0
            for _y in range(_h):
                for _x in range(_w):
                    _r, _g, _b, _a = _img.getpixel((_x, _y))
                    if _a > 128 and matcher(_r, _g, _b):
                        _n += 1
            counts.append(_n)
        return counts

    _seg_frames, _, _, _ = animate_rigged(
        _make_two_segment_png(),
        "run",
        16,
        128,
        rig=_fake_straight_rig(),
        segment_mask=None,
        keep_background=False,
    )
    _is_orange = lambda r, g, b: r > 180 and 70 < g < 170 and b < 90  # noqa: E731
    _is_purple = lambda r, g, b: 110 < r < 190 and g < 120 and b > 150  # noqa: E731
    _is_crotch = lambda r, g, b: r > 150 and g > 180 and b < 130  # noqa: E731
    _orange = _band_counts(_seg_frames, _is_orange)
    _purple = _band_counts(_seg_frames, _is_purple)
    _crotch = _band_counts(_seg_frames, _is_crotch)
    # 不变量一（膝下单次渲染）：小腿色带像素数逐帧不得膨胀——旧代码里父段
    # （大腿层）按大腿角再渲染一份膝下拷贝、立柱再盖一份不旋转拷贝，run 的
    # 58° 膝弯让三份拷贝几乎不重叠（计数膨胀 ~1.5x+）
    _orange_base = max(1, sorted(_orange)[len(_orange) // 2])
    _orange_growth = max(_orange) / _orange_base
    check(
        "ghost fix: shin band rendered once (count growth < 1.25x)",
        len(_orange) == 16 and _orange_growth < 1.25,
        f"growth={_orange_growth:.2f} counts={_orange}",
    )
    # 不变量二（肘下单次渲染·回归上界）：前臂色带同理。注意肘屈与摆臂
    # 行程耦合（旧代码里两份拷贝部分重合），本断言是独占所有权裁剪的
    # 回归上界，判别性由不变量一承担（旧代码实测 1.41 vs 新 1.08）
    _arm_frames, _, _, _ = animate_rigged(
        _make_two_segment_png(),
        "walk",
        16,
        128,
        rig=_fake_straight_rig(),
        config={"arm": 2.5},
        segment_mask=None,
        keep_background=False,
    )
    _purple = _band_counts(_arm_frames, _is_purple)
    _purple_base = max(1, sorted(_purple)[len(_purple) // 2])
    _purple_growth = max(_purple) / _purple_base
    check(
        "ghost fix: forearm band rendered once (count growth < 1.25x)",
        len(_purple) == 16 and _purple_growth < 1.25,
        f"growth={_purple_growth:.2f} counts={_purple}",
    )
    # 不变量三（立柱裁到膝）：立柱色带不得出现在膝线之下（旧版矩形到脚底，
    # 把未旋转的原姿态小腿列盖在每一帧上）
    _knee_y = 93
    _pillar_leak = 0
    for _w, _h, _rgba in _seg_frames:
        _img = _TImg.frombytes("RGBA", (_w, _h), bytes(_rgba))
        for _y in range(_h):
            for _x in range(_w):
                _r, _g, _b, _a = _img.getpixel((_x, _y))
                if _a > 128 and _is_crotch(_r, _g, _b) and _y > _knee_y + 14:
                    _pillar_leak += 1
    check(
        "ghost fix: crotch pillar trimmed at knee (no pixels below knee line)",
        _pillar_leak == 0,
        f"{_pillar_leak} pillar pixels below knee",
    )
    # 不变量四（立柱仍履职）：镜像摆腿最大帧里中缝楔形仍被立柱像素填补
    # ——"只填洞"门控不能把填洞能力也门没了
    check(
        "ghost fix: crotch pillar still fills stance gap (present in mirror frames)",
        min(_crotch[0], _crotch[8]) > 0,
        f"counts at mirror frames = {_crotch[0]}, {_crotch[8]}",
    )

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
