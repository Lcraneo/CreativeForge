"""Phase 2 — Character Rig / character-bound skeletal animation tests.

Run: python tests/test_character_rig.py  (also pytest-compatible)

Covers the three deliverables the phase spec names:
    * two characters have distinct rigs and distinct output frames
    * skeletal mode requires a real source (no silent default-character fallback)
    * the service passes the asset source into the skeletal pipeline
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from artgen import build_rig, render_character_view  # noqa: E402
from artgen.riganim import animate_rigged  # noqa: E402
from studio.backend.animation_service.service import AnimationService  # noqa: E402

BLUE = {"outline": "#1f2a44", "base": "#4aa3e0", "accent": "#ffd166",
        "hair": "#2b6cb0", "skin": "#ffe9d6", "eyes": "#2b2b2b", "metal": "#cfd8e3"}
RED = {"outline": "#2a1414", "base": "#e5533d", "accent": "#ffd166",
       "hair": "#3a1f1f", "skin": "#ffe0c0", "eyes": "#1a1a1a", "metal": "#c0c0c0"}


def _png(seed, palette, size=256):
    return bytes(render_character_view({"palette": palette, "seed": seed}, "front", size))


def test_two_characters_have_distinct_rigs_and_outputs():
    a = _png(7, BLUE)
    b = _png(99, RED)
    rig_a = build_rig(a, 256)
    rig_b = build_rig(b, 256)
    assert rig_a["source_hash"] != rig_b["source_hash"], "rigs must be character-specific"
    frames_a, _, _, _ = animate_rigged(a, "walk", 6, 256)
    frames_b, _, _, _ = animate_rigged(b, "walk", 6, 256)
    assert frames_a[0][2] != frames_b[0][2], "different characters must produce different frames"


def test_skeletal_requires_a_real_source():
    service = AnimationService(tempfile.mkdtemp())
    try:
        service.create(asset=None, image_bytes=None, skeletal=True, action="walk")
    except ValueError:
        return
    raise AssertionError("skeletal mode must raise when there is no real source")


def test_service_passes_asset_source_into_skeletal_pipeline():
    service = AnimationService(tempfile.mkdtemp())
    meta = service.create(
        asset=None, image_bytes=_png(7, BLUE), skeletal=True,
        action="walk", fps=6, duration=1.0, size=192,
    )
    assert meta["skeletal"] is True
    assert meta["source"] == "skeletal"
    assert meta.get("rig", {}).get("source_hash"), "rig summary must carry source_hash"
    assert meta.get("falign", {}).get("overall", 0) > 0, "falign report expected"
    assert meta["frame_count"] >= 2


def _run():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
            passed += 1
        except Exception as error:  # noqa: BLE001
            print(f"[FAIL] {name} -- {error}")
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run())
