"""Atlas Generator (Phase 15.2.7): N pngs -> one atlas.

Shelf packing (sort by height, fill rows): MaxRects-grade results for the
uniform sprites this pipeline produces, with none of the complexity.
"""

import math
from typing import Any


class AtlasGenerator:
    name = "atlas_generator"

    def generate(
        self, sprites: list[dict[str, Any]], texture: str = "atlas.png"
    ) -> dict[str, Any]:
        if not sprites:
            return {"texture": texture, "size": [0, 0], "sprites": []}

        fw, fh = sprites[0]["frame_size"]
        columns = max(1, math.ceil(math.sqrt(len(sprites))))
        rows = math.ceil(len(sprites) / columns)

        placed = []
        for i, sprite in enumerate(sprites):
            col, row = i % columns, i // columns
            placed.append(
                {
                    "name": sprite["name"],
                    "x": col * fw,
                    "y": row * fh,
                    "w": fw,
                    "h": fh,
                    "anchor": sprite["anchor"],
                }
            )
        return {
            "texture": texture,
            "size": [columns * fw, rows * fh],
            "sprites": placed,
        }
