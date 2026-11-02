"""Regression tests for the fixed three-stage 2.5D PVE campaign."""

from copy import deepcopy

from studio.backend.scene_service.compiler import (
    PVE_STAGE_COUNTS,
    compile_pve,
    validate_pve,
)


def _campaign(difficulty="normal", prompt="", enemy_pool=None, seed=1):
    return compile_pve(
        {"difficulty": difficulty}, seed=seed, prompt=prompt, enemy_pool=enemy_pool
    )


def test_generated_campaign_has_exactly_three_stages():
    for difficulty in ("easy", "normal", "hard"):
        campaign = _campaign(difficulty)
        result = validate_pve(campaign, difficulty)
        assert result["ok"], result["issues"]
        assert campaign["schema_version"] == 2
        stages = campaign["stages"]
        assert len(stages) == 3
        assert [stage["id"] for stage in stages] == ["stage_1", "stage_2", "stage_3"]
        assert [stage["kind"] for stage in stages] == ["minion", "minion", "boss"]
        assert len(stages[0]["enemies"]) == PVE_STAGE_COUNTS[0]
        assert len(stages[1]["enemies"]) == PVE_STAGE_COUNTS[1]
        assert len(stages[2]["enemies"]) == PVE_STAGE_COUNTS[2]
        assert all(enemy["kind"] == "minion" for enemy in stages[0]["enemies"])
        assert all(enemy["kind"] == "minion" for enemy in stages[1]["enemies"])
        assert [enemy["kind"] for enemy in stages[2]["enemies"]] == ["boss"]
        for stage in stages:
            arena = stage["arena"]
            assert arena["width"] > 0 and arena["depth"] > 0
            assert 0 <= arena["spawn_x"] <= arena["width"]
            assert 0 <= arena["spawn_y"] <= arena["depth"]
            assert "background_url" in stage
        metrics = result["combat_metrics"]
        assert metrics["quality_ok"], metrics
        assert 90 <= metrics["estimated_duration_seconds"] <= 160
        assert metrics["minimum_telegraph_seconds"] >= 0.35


def test_campaign_drops_legacy_layout_keys():
    campaign = _campaign()
    assert "arena_segments" not in campaign
    assert "hazards" not in campaign
    assert "covers" not in campaign
    assert "encounters" not in campaign
    for stage in campaign["stages"]:
        for key in ("arena_segments", "hazards", "covers", "encounters", "platforms"):
            assert key not in stage


def test_stage_two_prefers_a_different_minion_template():
    pool = [
        {
            "id": "minion_a",
            "name": "甲小怪",
            "role": "minion",
            "status": "ready",
            "asset_id": "ast_minion_a",
            "behavior": "chaser",
            "tags": ["beast"],
            "stats": {"max_hp": 3, "speed": 70, "damage": 1, "attack_interval": 2.4, "display_height": 92},
        },
        {
            "id": "minion_b",
            "name": "乙小怪",
            "role": "minion",
            "status": "ready",
            "asset_id": "ast_minion_b",
            "behavior": "shooter",
            "tags": ["ranged"],
            "stats": {"max_hp": 4, "speed": 60, "damage": 1, "attack_interval": 2.0, "display_height": 96},
        },
    ]
    campaign = _campaign(prompt="远程小怪", enemy_pool=pool)
    first = {(e["profile_id"], e["asset_id"]) for e in campaign["stages"][0]["enemies"]}
    second = {(e["profile_id"], e["asset_id"]) for e in campaign["stages"][1]["enemies"]}
    assert len(first) == 1 and len(second) == 1
    assert first != second


def test_custom_profile_stats_are_preserved():
    pool = [
        {
            "id": "custom_minion",
            "name": "自定义小怪",
            "role": "minion",
            "status": "ready",
            "asset_id": "ast_custom_minion",
            "behavior": "charger",
            "tags": ["ranged", "fire"],
            "stats": {"max_hp": 5, "speed": 61, "damage": 2, "attack_interval": 1.8, "display_height": 98},
        },
        {
            "id": "custom_boss",
            "name": "自定义 Boss",
            "role": "boss",
            "status": "ready",
            "asset_id": "ast_custom_boss",
            "behavior": "guardian",
            "tags": ["armored", "fire"],
            "stats": {"max_hp": 32, "speed": 56, "damage": 3, "attack_interval": 1.2, "display_height": 232},
        },
    ]
    campaign = _campaign(prompt="远程火焰重甲守关", enemy_pool=pool)
    assert validate_pve(campaign, "normal")["ok"]
    assert campaign["stages"][0]["enemies"][0]["max_hp"] == 5
    boss = campaign["stages"][2]["enemies"][0]
    assert boss["profile_id"] == "custom_boss"
    assert boss["max_hp"] == 32


def test_rejects_legacy_layout_keys():
    campaign = _campaign()
    broken = deepcopy(campaign)
    broken["arena_segments"] = [{"id": "legacy", "template": "open"}]
    result = validate_pve(broken, "normal")
    assert not result["ok"]

    broken = deepcopy(campaign)
    broken["stages"][0]["hazards"] = [{"id": "vent", "x": 10}]
    result = validate_pve(broken, "normal")
    assert not result["ok"]

    broken = deepcopy(campaign)
    broken["stages"][0]["covers"] = [{"id": "cover", "x": 10}]
    assert not validate_pve(broken, "normal")["ok"]

    broken = deepcopy(campaign)
    broken["stages"][0]["encounters"] = [{"id": "fight"}]
    assert not validate_pve(broken, "normal")["ok"]


def test_rejects_boss_in_minion_stage_and_bad_boss_count():
    broken = deepcopy(_campaign())
    broken["stages"][1]["enemies"][0]["kind"] = "boss"
    result = validate_pve(broken, "normal")
    assert not result["ok"]
    assert any("不能出现 Boss" in issue for issue in result["issues"])

    broken = deepcopy(_campaign())
    broken["stages"][2]["enemies"].append(deepcopy(broken["stages"][2]["enemies"][0]))
    result = validate_pve(broken, "normal")
    assert not result["ok"]
    assert any("有且只有一个 Boss" in issue for issue in result["issues"])

    broken = deepcopy(_campaign())
    broken["stages"][2]["enemies"] = []
    assert not validate_pve(broken, "normal")["ok"]


def test_rejects_out_of_bounds_enemies_and_invalid_stats():
    broken = deepcopy(_campaign())
    broken["stages"][0]["enemies"][0]["x"] = 99999
    assert not validate_pve(broken, "normal")["ok"]

    broken = deepcopy(_campaign())
    broken["stages"][0]["enemies"][0]["max_hp"] = 0
    assert not validate_pve(broken, "normal")["ok"]

    broken = deepcopy(_campaign())
    broken["stages"][0]["enemies"][0]["behavior"] = "unknown"
    assert not validate_pve(broken, "normal")["ok"]

    broken = deepcopy(_campaign())
    broken["schema_version"] = 1
    assert not validate_pve(broken, "normal")["ok"]
