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

        self.service = SceneService(
            store=self.store,
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

    def test_rejects_non_parkour_and_invalid_difficulty(self):
        non_parkour = self.client.post(
            "/api/scenes", json={"prompt": "arena", "gameplay": "pve", "difficulty": "normal"}
        )
        self.assertEqual(non_parkour.status_code, 422)
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


if __name__ == "__main__":
    unittest.main()
