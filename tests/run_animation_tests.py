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
        "id": "a1", "asset_id": "astQ", "status": "running", "total": 3, "created_at": 3.0,
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

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
