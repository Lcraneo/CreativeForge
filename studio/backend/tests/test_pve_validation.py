"""Regression tests for encounter layouts that would stall or skip combat."""

from copy import deepcopy

from studio.backend.scene_service.compiler import compile_pve, validate_pve


def test_generated_pve_layouts_validate():
    for length in ("short", "medium", "long"):
        for difficulty in ("easy", "normal", "hard"):
            level = compile_pve({"length": length, "difficulty": difficulty}, seed=1)
            assert validate_pve(level, difficulty)["ok"]
            assert level["hazards"]
            assert any(p["kind"] == "floating" for p in level["platforms"])
            assert {segment["template"] for segment in level["arena_segments"]} == {
                "open", "dual_platform", "hazard_corridor", "boss_cover"
            }
            assert len(level["covers"]) == 2
            metrics = validate_pve(level, difficulty)["combat_metrics"]
            assert metrics["quality_ok"], metrics
            assert 90 <= metrics["estimated_duration_seconds"] <= 160
            assert metrics["minimum_telegraph_seconds"] >= 0.35


def test_rejects_unsafe_vent_and_unreachable_platform():
    level = compile_pve({"length": "medium", "difficulty": "normal"}, seed=1)
    hazard = level["hazards"][0]
    bridge = next(
        platform for platform in level["platforms"]
        if platform["kind"] == "floating"
        and platform["x"] <= hazard["x"]
        and platform["x"] + platform["width"] >= hazard["x"] + hazard["width"]
    )
    bridge["y"] = 10
    result = validate_pve(level, "normal")
    assert not result["ok"]
    assert "危险区域缺少可达的安全桥面" in result["issues"]

    level = compile_pve({"length": "medium", "difficulty": "normal"}, seed=1)
    level["covers"][0]["height"] = 20
    assert "Boss 掩体尺寸无效" in validate_pve(level, "normal")["issues"]

    level = compile_pve({"length": "medium", "difficulty": "normal"}, seed=1)
    level["arena_segments"].pop()
    assert not validate_pve(level, "normal")["ok"]


def test_rejects_unassigned_and_repeated_enemies_and_early_boss():
    level = compile_pve({"length": "medium", "difficulty": "normal"}, seed=1)
    broken = deepcopy(level)
    broken["encounters"][0]["enemy_ids"].append("boss_1")
    result = validate_pve(broken, "normal")
    assert not result["ok"]
    assert "敌人被重复分配到遭遇战" in result["issues"]

    broken = deepcopy(level)
    broken["encounters"][0]["enemy_ids"].clear()
    result = validate_pve(broken, "normal")
    assert "遭遇战没有敌人" in result["issues"]
    assert "存在未分配遭遇战的敌人" in result["issues"]

    broken = deepcopy(level)
    broken["encounters"][0]["kind"] = "boss"
    assert not validate_pve(broken, "normal")["ok"]
