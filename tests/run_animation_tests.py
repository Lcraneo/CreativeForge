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

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
