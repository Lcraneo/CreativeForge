"""Prompt-driven parkour scene compiler regression."""

import json
import unittest

from studio.backend.scene_service.compiler import (
    compile_parkour,
    normalize_intent,
    validate_parkour,
)


class SceneCompilerTests(unittest.TestCase):
    def _intent(self, difficulty="normal", length="medium", prompt="雪夜古堡"):
        return normalize_intent(
            {
                "title": "雪夜古堡",
                "environment": "snow",
                "length": length,
                "features": [
                    "gaps",
                    "rising_platforms",
                    "floating_platforms",
                    "long_jumps",
                ],
                "palette": {
                    "skyTop": "#112233",
                    "skyBottom": "#445566",
                    "ground": "#778899",
                    "floating": "#aabbcc",
                    "accent": "#ddeeff",
                },
            },
            prompt,
            difficulty,
        )

    def test_every_difficulty_and_length_is_reachable(self):
        for difficulty in ("easy", "normal", "hard"):
            for length in ("short", "medium", "long"):
                intent = self._intent(difficulty, length)
                for seed in range(40):
                    level = compile_parkour(intent, seed)
                    validation = validate_parkour(level, difficulty)
                    self.assertTrue(validation["ok"], (difficulty, length, seed, validation))

    def test_same_seed_is_deterministic(self):
        intent = self._intent()
        first = compile_parkour(intent, 20261031)
        second = compile_parkour(intent, 20261031)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_invalid_model_fields_fall_back_to_safe_values(self):
        intent = normalize_intent(
            {
                "environment": "unknown",
                "length": "impossible",
                "features": ["script"],
                "palette": {"skyTop": "red"},
            },
            "熔岩火山，长跳",
            "hard",
        )
        self.assertEqual(intent["environment"], "lava")
        self.assertEqual(intent["length"], "medium")
        self.assertEqual(intent["difficulty"], "hard")
        self.assertEqual(intent["features"], ["gaps", "rising_platforms", "long_jumps"])
        self.assertRegex(intent["palette"]["skyTop"], r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()
