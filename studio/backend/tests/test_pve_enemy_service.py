"""PVE enemy forge and semantic roster selection."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.backend.api.pve_routes import build_pve_router
from studio.backend.pve_service.service import PveEnemyService, PveEnemyStore
from studio.backend.scene_service.compiler import compile_pve, normalize_intent


class _Settings:
    def effective(self):
        return {
            "enabled": True,
            "api_key": "test",
            "base_url": "http://model",
            "chat_model": "test-model",
        }


class _Runtime:
    model_settings = _Settings()


class PveEnemyServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "pve_enemies.json")
        self.store = PveEnemyStore(self.path)

    def test_semantic_analysis_and_profile_persistence(self):
        service = PveEnemyService(
            _Runtime(),
            store=self.store,
            chat_fn=lambda _prompt, _settings: json.dumps(
                {
                    "name": "霜甲冲锋兽",
                    "summary": "披覆冰甲的冲锋型小怪",
                    "tags": ["fast", "armored", "ice", "beast"],
                    "behavior": "charger",
                    "element": "ice",
                },
                ensure_ascii=False,
            ),
        )
        analysis = service._analyze(
            "冰霜机械冲锋兽，披覆重甲，会高速撞击",
            "minion",
            "hard",
            _Runtime().model_settings.effective(),
        )
        stats = service._stats("minion", "hard", analysis["behavior"], analysis["tags"])
        self.assertEqual(analysis["name"], "霜甲冲锋兽")
        self.assertEqual(analysis["behavior"], "charger")
        self.assertIn("armored", analysis["tags"])
        self.assertGreater(stats["speed"], 88)
        self.assertEqual(stats["max_hp"], 4)

        record = {
            "id": "pve_test01",
            "name": analysis["name"],
            "role": "minion",
            "prompt": "冰霜机械冲锋兽",
            "summary": analysis["summary"],
            "tags": analysis["tags"],
            "behavior": analysis["behavior"],
            "element": analysis["element"],
            "projectile_color": "#8feaff",
            "asset_id": "ast_custom",
            "status": "ready",
            "builtin": False,
            "stats": stats,
            "created_at": 1,
            "updated_at": 1,
        }
        self.store.save(record)
        restored = PveEnemyStore(self.path)
        self.assertEqual(restored.get("pve_test01")["name"], "霜甲冲锋兽")
        self.assertIn("builtin_slime", {item["id"] for item in restored.list()})

    def test_builtin_assets_are_claimed_by_enemy_pool(self):
        class History:
            def __init__(self):
                self.patches = []

            def patch_asset(self, asset_id, patch):
                self.patches.append((asset_id, patch))
                return True

        runtime = _Runtime()
        runtime.history = History()
        PveEnemyService(runtime, store=self.store)

        self.assertEqual(
            runtime.history.patches,
            [
                ("ast64960", {"pve_enemy": True, "pve_role": "minion"}),
                ("ast60574", {"pve_enemy": True, "pve_role": "boss"}),
            ],
        )

    def test_scene_selects_custom_enemy_by_prompt_and_builds_campaign(self):
        profile = {
            "id": "pve_mechanic",
            "name": "霜甲冲锋兽",
            "role": "minion",
            "prompt": "冰霜机械冲锋兽",
            "summary": "冰甲冲锋小怪",
            "tags": ["fast", "armored", "ice", "beast"],
            "behavior": "charger",
            "element": "ice",
            "projectile_color": "#8feaff",
            "asset_id": "ast_custom_minion",
            "status": "ready",
            "builtin": False,
            "stats": {
                "max_hp": 7,
                "speed": 111,
                "damage": 2,
                "attack_interval": 1.8,
                "display_height": 104,
            },
            "created_at": 2,
            "updated_at": 2,
        }
        intent = normalize_intent(
            {
                "title": "机械冰原",
                "environment": "snow",
                "difficulty": "hard",
                "length": "medium",
            },
            "冰原上的霜甲冲锋兽",
            "hard",
        )
        level = compile_pve(intent, 42, "冰原上的霜甲冲锋兽", [profile])
        minion = level["stages"][0]["enemies"][0]
        self.assertEqual(minion["asset_id"], "ast_custom_minion")
        self.assertEqual(minion["max_hp"], 7)
        self.assertEqual(minion["behavior"], "charger")
        self.assertEqual(level["stages"][2]["kind"], "boss")
        self.assertEqual(len(level["stages"][2]["enemies"]), 1)

    def test_enemy_api_lists_independent_roster_and_validates_role(self):
        service = PveEnemyService(_Runtime(), store=self.store)
        app = FastAPI()
        app.include_router(build_pve_router(service))
        client = TestClient(app)
        listed = client.get("/api/pve/enemies")
        self.assertEqual(listed.status_code, 200)
        self.assertIn(
            "builtin_slime",
            {enemy["id"] for enemy in listed.json()["enemies"]},
        )
        response = client.post(
            "/api/pve/enemies/generate",
            json={"prompt": "冰霜兽", "role": "npc", "difficulty": "normal"},
        )
        self.assertEqual(response.status_code, 422)

    def test_enemy_api_deletes_custom_profiles_but_keeps_builtins(self):
        record = {
            "id": "pve_removable",
            "name": "待删除敌人",
            "role": "minion",
            "status": "ready",
            "builtin": False,
            "asset_id": "ast_remove",
            "stats": {"max_hp": 3},
            "created_at": 1,
            "updated_at": 1,
        }
        self.store.save(record)
        service = PveEnemyService(_Runtime(), store=self.store)
        app = FastAPI()
        app.include_router(build_pve_router(service))
        client = TestClient(app)

        removed = client.delete("/api/pve/enemies/pve_removable")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["removed"], "pve_removable")
        self.assertIsNone(PveEnemyStore(self.path).get("pve_removable"))

        builtin = client.delete("/api/pve/enemies/builtin_slime")
        self.assertEqual(builtin.status_code, 409)
        self.assertIsNotNone(client.get("/api/pve/enemies/builtin_slime").json())

    def test_exact_boss_name_beats_generic_element_tags(self):
        boss = {
            "id": "pve_lava_boss",
            "name": "熔岩巨像",
            "role": "boss",
            "prompt": "熔岩机械巨像",
            "summary": "熔岩守关 Boss",
            "tags": ["armored", "fire"],
            "behavior": "shooter",
            "element": "fire",
            "projectile_color": "#ff9b62",
            "asset_id": "ast_custom_boss",
            "status": "ready",
            "builtin": False,
            "stats": {
                "max_hp": 28,
                "speed": 45,
                "damage": 2,
                "attack_interval": 1.4,
                "display_height": 224,
            },
            "created_at": 2,
            "updated_at": 2,
        }
        intent = normalize_intent({}, "冰霜小怪与熔岩巨像", "normal")
        level = compile_pve(
            intent,
            7,
            "机械冰霜狼巡逻，尽头由熔岩巨像守关",
            [boss],
        )
        scene_boss = level["stages"][2]["enemies"][0]
        self.assertEqual(scene_boss["name"], "熔岩巨像")
        self.assertEqual(scene_boss["asset_id"], "ast_custom_boss")


    def test_interrupted_generation_is_marked_failed_and_persisted(self):
        payload = {
            "enemies": [
                {
                    "id": "pve_stuck",
                    "name": "霜铠巨像王",
                    "role": "boss",
                    "prompt": "守关巨像",
                    "asset_id": "ast_stuck",
                    "status": "generating_actions",
                    "builtin": False,
                    "stats": {"max_hp": 28},
                    "created_at": 1,
                    "updated_at": 1,
                }
            ]
        }
        Path(self.path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        store = PveEnemyStore(self.path)
        self.assertEqual(store.get("pve_stuck")["status"], "failed")
        saved = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(saved["enemies"][0]["status"], "failed")

    def test_retry_requeues_failed_enemy_with_existing_asset(self):
        record = {
            "id": "pve_retry",
            "name": "霜铠巨像王",
            "role": "boss",
            "prompt": "守关巨像",
            "asset_id": "ast_retry",
            "status": "failed",
            "builtin": False,
            "stats": {"max_hp": 28},
            "created_at": 1,
            "updated_at": 1,
        }
        self.store.save(record)
        service = PveEnemyService(_Runtime(), store=self.store)
        app = FastAPI()
        app.include_router(build_pve_router(service))
        client = TestClient(app)

        response = client.post("/api/pve/enemies/pve_retry/retry")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "generating_actions")


if __name__ == "__main__":
    unittest.main()
