"""Scene generation API and persistence regression."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.scene_routes import build_scene_router
from studio.backend.scene_service.service import SceneService, SceneStore


class SceneApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.png"
        self.source.write_bytes(b"\x89PNG\r\n\x1a\nscene")
        self.store = SceneStore(str(self.root / "scenes.json"))
        self.image_prompts = []

        def fake_image(prompt, _settings):
            self.image_prompts.append(prompt)
            return {"file": str(self.source)}

        self.pve_profiles = [
            {
                "id": "test_slime",
                "name": "测试史莱姆",
                "role": "minion",
                "status": "ready",
                "builtin": True,
                "asset_id": "ast64960",
                "behavior": "chaser",
                "element": "toxic",
                "projectile_color": "#9fe56f",
                "tags": ["toxic", "beast"],
                "stats": {
                    "max_hp": 3,
                    "speed": 72,
                    "damage": 1,
                    "attack_interval": 2.4,
                    "display_height": 92,
                },
            },
            {
                "id": "test_boss",
                "name": "测试冰龙",
                "role": "boss",
                "status": "ready",
                "builtin": True,
                "asset_id": "ast60574",
                "behavior": "guardian",
                "element": "ice",
                "projectile_color": "#8feaff",
                "tags": ["ice", "flying"],
                "stats": {
                    "max_hp": 24,
                    "speed": 42,
                    "damage": 2,
                    "attack_interval": 1.35,
                    "display_height": 224,
                },
            },
            {
                "id": "alt_minion",
                "name": "替换小怪",
                "role": "minion",
                "status": "ready",
                "builtin": False,
                "asset_id": "ast_alt_minion",
                "behavior": "shooter",
                "element": "fire",
                "projectile_color": "#ff9b62",
                "tags": ["ranged", "fire"],
                "stats": {
                    "max_hp": 5,
                    "speed": 61,
                    "damage": 2,
                    "attack_interval": 1.8,
                    "display_height": 98,
                },
            },
            {
                "id": "alt_boss",
                "name": "替换 Boss",
                "role": "boss",
                "status": "ready",
                "builtin": False,
                "asset_id": "ast_alt_boss",
                "behavior": "charger",
                "element": "fire",
                "projectile_color": "#ff9b62",
                "tags": ["armored", "fire"],
                "stats": {
                    "max_hp": 32,
                    "speed": 56,
                    "damage": 3,
                    "attack_interval": 1.2,
                    "display_height": 232,
                },
            },
        ]

        self.service = SceneService(
            store=self.store,
            pve_enemy_provider=lambda: self.pve_profiles,
            settings_provider=lambda: {
                "enabled": True,
                "api_key": "test",
                "chat_model": "qwen3-omni-flash",
                "model": "wanx2.1-t2i-turbo",
            },
            chat_fn=lambda _prompt, _settings: json.dumps(
                {
                    "title": "雪夜古堡",
                    "environment": "snow",
                    "mood": "月光下破碎的城堡",
                    "difficulty": "normal",
                    "length": "medium",
                    "features": ["gaps", "rising_platforms"],
                },
                ensure_ascii=False,
            ),
            image_fn=fake_image,
        )
        app = FastAPI()
        app.include_router(build_scene_router(self.service))
        self.client = TestClient(app)

    def test_create_poll_list_background_delete(self):
        with patch(
            "studio.backend.scene_service.service.safe_generated_path",
            side_effect=lambda _name: str(self.source),
        ):
            created = self.client.post(
                "/api/scenes",
                json={
                    "prompt": "雪夜古堡，连续上升平台",
                    "gameplay": "parkour",
                    "difficulty": "normal",
                },
            )
            self.assertEqual(created.status_code, 202)
            scene_id = created.json()["scene_id"]
            self.assertRegex(scene_id, r"^scene_[0-9a-f]{12}$")

            scene = None
            for _ in range(100):
                response = self.client.get(f"/api/scenes/{scene_id}")
                self.assertEqual(response.status_code, 200)
                scene = response.json()
                if scene["status"] != "generating":
                    break
                time.sleep(0.01)

            self.assertEqual(scene["status"], "ready", scene)
            self.assertEqual(scene["title"], "雪夜古堡")
            self.assertTrue(scene["gameplay"]["validation"]["ok"])
            self.assertTrue(scene["gameplay"]["level"]["platforms"])
            self.assertEqual(len(scene["theme"]["background_urls"]), 5)
            self.assertEqual(
                scene["theme"]["background_url"],
                f"/api/scenes/{scene_id}/backgrounds/0.png",
            )
            self.assertEqual(scene["generation"]["background_total"], 5)
            self.assertEqual(scene["generation"]["background_done"], 5)
            self.assertEqual(len(self.image_prompts), 5)
            self.assertEqual(len(set(self.image_prompts)), 5)

            listed = self.client.get("/api/scenes").json()["scenes"]
            self.assertEqual(listed[0]["id"], scene_id)
            self.assertEqual(listed[0]["background_count"], 5)
            for index, url in enumerate(scene["theme"]["background_urls"]):
                background = self.client.get(url)
                self.assertEqual(background.status_code, 200)
                self.assertEqual(background.content, self.source.read_bytes())
                self.assertTrue((self.root / f"{scene_id}_{index}.png").exists())

        restored = SceneStore(str(self.root / "scenes.json")).get(scene_id)
        self.assertEqual(restored["status"], "ready")
        self.assertTrue(self.client.delete(f"/api/scenes/{scene_id}").json()["removed"])
        self.assertFalse((self.root / f"{scene_id}_0.png").exists())
        self.assertFalse((self.root / f"{scene_id}_4.png").exists())

    def test_pve_scene_has_three_stage_campaign(self):
        with patch(
            "studio.backend.scene_service.service.safe_generated_path",
            side_effect=lambda _name: str(self.source),
        ):
            created = self.client.post(
                "/api/scenes",
                json={"prompt": "冰霜古堡战斗", "gameplay": "pve", "difficulty": "hard"},
            )
            self.assertEqual(created.status_code, 202)
            scene_id = created.json()["scene_id"]
            scene = None
            for _ in range(100):
                scene = self.client.get(f"/api/scenes/{scene_id}").json()
                if scene["status"] != "generating":
                    break
                time.sleep(0.01)

        self.assertEqual(scene["status"], "ready", scene)
        gameplay = scene["gameplay"]
        self.assertEqual(gameplay["type"], "pve")
        self.assertTrue(gameplay["validation"]["ok"])
        self.assertIsNone(gameplay["level"])
        self.assertFalse(gameplay.get("legacy"))
        campaign = gameplay["campaign"]
        self.assertEqual(campaign["schema_version"], 2)
        stages = campaign["stages"]
        self.assertEqual(len(stages), 3)
        self.assertEqual([stage["id"] for stage in stages], ["stage_1", "stage_2", "stage_3"])
        self.assertEqual([stage["kind"] for stage in stages], ["minion", "minion", "boss"])
        self.assertEqual(len(stages[0]["enemies"]), 4)
        self.assertEqual(len(stages[1]["enemies"]), 6)
        self.assertEqual(len(stages[2]["enemies"]), 1)
        self.assertEqual(stages[2]["enemies"][0]["kind"], "boss")
        self.assertTrue(all(enemy["kind"] == "minion" for enemy in stages[0]["enemies"]))
        self.assertTrue(all(enemy["kind"] == "minion" for enemy in stages[1]["enemies"]))
        for stage in stages:
            for key in ("arena_segments", "hazards", "covers", "encounters", "platforms"):
                self.assertNotIn(key, stage)
            self.assertTrue(stage["background_url"])

        background_urls = scene["theme"]["background_urls"]
        self.assertEqual(len(background_urls), 3)
        self.assertEqual(len(set(background_urls)), 3)
        self.assertEqual(scene["generation"]["background_total"], 3)
        self.assertEqual(len(self.image_prompts), 3)
        for stage, url in zip(stages, background_urls):
            self.assertEqual(stage["background_url"], url)

        listed = self.client.get("/api/scenes").json()["scenes"]
        self.assertEqual(listed[0]["gameplay_type"], "pve")
        self.assertEqual(listed[0]["enemy_count"], 11)
        self.assertEqual(listed[0]["background_count"], 3)
        self.assertFalse(listed[0]["legacy"])

    def test_pve_enemy_sequence_can_be_replaced_per_stage(self):
        with patch(
            "studio.backend.scene_service.service.safe_generated_path",
            side_effect=lambda _name: str(self.source),
        ):
            scene = self.service.create_sync(
                "冰霜古堡战斗", "normal", seed=17, gameplay="pve"
            )
        stages = scene["gameplay"]["campaign"]["stages"]
        stage_one_ids = [enemy["id"] for enemy in stages[0]["enemies"]]
        stage_two_ids = [
            "alt_minion" if enemy["kind"] != "boss" else "alt_boss"
            for enemy in stages[1]["enemies"]
        ]
        response = self.client.put(
            f"/api/scenes/{scene['id']}/pve/enemy-sequence",
            json={"profile_ids": stage_two_ids, "stage_id": "stage_2"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        updated_stages = updated["gameplay"]["campaign"]["stages"]
        self.assertEqual(
            [enemy["id"] for enemy in updated_stages[0]["enemies"]], stage_one_ids
        )
        self.assertTrue(
            all(enemy["name"] == "替换小怪" for enemy in updated_stages[1]["enemies"])
        )
        self.assertEqual(
            updated_stages[2]["enemies"][0]["name"],
            stages[2]["enemies"][0]["name"],
        )
        self.assertTrue(updated["gameplay"]["validation"]["ok"])

        profile_ids = [
            "alt_boss" if enemy["kind"] == "boss" else "alt_minion"
            for stage in updated_stages
            for enemy in stage["enemies"]
        ]
        response = self.client.put(
            f"/api/scenes/{scene['id']}/pve/enemy-sequence",
            json={"profile_ids": profile_ids},
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        boss = updated["gameplay"]["campaign"]["stages"][2]["enemies"][0]
        self.assertEqual(boss["name"], "替换 Boss")
        self.assertEqual(boss["max_hp"], 32)
        self.assertIn("替换 Boss", updated["gameplay"]["campaign"]["stages"][2]["title"])

        invalid = [*profile_ids]
        invalid[-1] = "alt_minion"
        rejected = self.client.put(
            f"/api/scenes/{scene['id']}/pve/enemy-sequence",
            json={"profile_ids": invalid},
        )
        self.assertEqual(rejected.status_code, 422)

    def test_legacy_pve_scene_is_marked_and_cannot_play(self):
        record = {
            "id": "scene_0123456789ab",
            "title": "旧版战斗关卡",
            "prompt": "旧版 PVE",
            "status": "ready",
            "theme": {"background_url": None, "background_urls": []},
            "created_at": 1,
            "updated_at": 1,
            "intent": {"difficulty": "normal", "length": "medium"},
            "gameplay": {
                "type": "pve",
                "difficulty": "normal",
                "level": {
                    "seed": "1",
                    "width": 3000,
                    "groundY": 348,
                    "spawnX": 120,
                    "goalX": 2900,
                    "platforms": [{"kind": "ground", "x": 0, "y": 348, "width": 3000}],
                    "enemies": [
                        {
                            "id": "slime_1",
                            "asset_id": "ast64960",
                            "name": "森林史莱姆",
                            "kind": "slime",
                            "x": 400,
                            "y": 300,
                        }
                    ],
                    "encounters": [],
                    "hazards": [],
                    "covers": [],
                    "arena_segments": [],
                },
            },
        }
        path = str(self.root / "legacy.json")
        (self.root / "legacy.json").write_text(
            json.dumps([record], ensure_ascii=False), encoding="utf-8"
        )
        store = SceneStore(path)
        loaded = store.get("scene_0123456789ab")
        self.assertTrue(loaded["gameplay"]["legacy"])
        self.assertTrue(loaded["gameplay"]["level"])

        service = SceneService(
            store=store,
            pve_enemy_provider=lambda: self.pve_profiles,
            settings_provider=lambda: {},
        )
        app = FastAPI()
        app.include_router(build_scene_router(service))
        client = TestClient(app)
        listed = client.get("/api/scenes").json()["scenes"]
        self.assertTrue(listed[0]["legacy"])
        rejected = client.put(
            "/api/scenes/scene_0123456789ab/pve/enemy-sequence",
            json={"profile_ids": ["alt_minion"]},
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("旧版 PVE", rejected.json()["detail"])

    def test_rejects_unknown_gameplay_and_invalid_difficulty(self):
        unknown = self.client.post(
            "/api/scenes", json={"prompt": "arena", "gameplay": "sandbox", "difficulty": "normal"}
        )
        self.assertEqual(unknown.status_code, 422)
        invalid_difficulty = self.client.post(
            "/api/scenes", json={"prompt": "castle", "gameplay": "parkour", "difficulty": "insane"}
        )
        self.assertEqual(invalid_difficulty.status_code, 422)

    def test_background_failure_still_produces_playable_scene(self):
        service = SceneService(
            store=SceneStore(str(self.root / "fallback.json")),
            settings_provider=lambda: {
                "enabled": True,
                "api_key": "test",
                "chat_model": "qwen3-omni-flash",
                "model": "wanx2.1-t2i-turbo",
            },
            chat_fn=lambda _prompt, _settings: json.dumps(
                {"title": "沙海", "environment": "desert", "length": "short"}
            ),
            image_fn=lambda _prompt, _settings: (_ for _ in ()).throw(RuntimeError("quota")),
        )
        scene = service.create_sync("沙漠短关卡", "easy", seed=7)
        self.assertEqual(scene["status"], "ready")
        self.assertIsNone(scene["theme"]["background_url"])
        self.assertEqual(scene["theme"]["background_urls"], [])
        self.assertTrue(scene["generation"]["warnings"])

    def test_background_count_follows_level_length(self):
        self.assertEqual(self.service.background_count("short"), 3)
        self.assertEqual(self.service.background_count("medium"), 5)
        self.assertEqual(self.service.background_count("long"), 7)
        self.assertEqual(self.service.background_count("short", "pve"), 3)
        self.assertEqual(self.service.background_count("medium", "pve"), 3)
        self.assertEqual(self.service.background_count("long", "pve"), 3)


if __name__ == "__main__":
    unittest.main()
