"""Vision Analyzer (Phase 13.5).

Understands *what* is in the image (semantic parts), not where the pixels
are — that is the segmentation engine's job.

MVP: deterministic keyword based part detection. Swap for a
GPT-4.1 Vision / Claude Vision call behind the same interface later.
"""

from typing import Any

DEFAULT_PARTS: list[tuple[str, str]] = [("body", "character")]

PART_KEYWORDS: list[tuple[str, str, str]] = [
    ("armor", "armor", ("机械", "甲", "战士", "骑士", "armor", "robot")),
    ("weapon", "weapon", ("剑", "刀", "枪", "weapon", "sword", "战士", "warrior")),
    ("effect", "effect", ("火", "焰", "光", "雷", "effect", "fire", "magic")),
]


class VisionAnalyzer:
    name = "vision_analyzer"

    async def analyze(self, image: str, goal: str | None = None) -> dict[str, Any]:
        text = f"{image} {goal or ''}".lower()
        parts = [{"name": name, "type": ptype} for name, ptype in DEFAULT_PARTS]
        for name, ptype, keywords in PART_KEYWORDS:
            if any(keyword.lower() in text for keyword in keywords):
                parts.append({"name": name, "type": ptype})
        return {"image": image, "parts": parts}
