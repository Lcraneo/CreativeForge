"""Phase 4 — Dynamic Creative Planner tests.

Run: python tests/test_dynamic_planner.py  (also pytest-compatible)

Verifies the plan is intent-driven (capabilities only when needed), not a fixed
Generation→PReCon→FAlign→GImport→QA pipeline.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from studio.backend.plan_service import build_plan  # noqa: E402


def _caps(plan):
    return [task["capability"] for task in plan["tasks"]]


def test_static_2d_does_not_force_processors():
    plan = build_plan("创建一个 2D 动漫风机械 Boss")
    caps = _caps(plan)
    assert "generation" in caps
    assert "PReCon" not in caps
    assert "FAlign" not in caps
    assert "GImport" not in caps


def test_pixel_animation_adds_precon_and_falign():
    plan = build_plan("创建一个冰霜机械猫，32×32 像素，做走路动画")
    caps = _caps(plan)
    assert "PReCon" in caps
    assert "FAlign" in caps
    assert "GImport" not in caps  # no engine requested


def test_engine_import_adds_gimport_with_engine():
    plan = build_plan("生成像素弓箭手并导入 Unity")
    caps = _caps(plan)
    assert "GImport" in caps
    engine = next(t for t in plan["tasks"] if t["capability"] == "GImport")
    assert engine["engine"] == "unity"
    assert plan["intent"]["engine"] == "unity"


def test_modify_existing_asset_starts_from_asset():
    plan = build_plan("把这个机器人改成火焰法师，再做攻击动画并导入 Unity", asset_id="ast-1")
    caps = _caps(plan)
    assert caps[0] == "edit_asset"
    assert "generation" not in caps
    assert "FAlign" in caps
    assert "GImport" in caps
    assert plan["mode"] == "modify"


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
