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

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
