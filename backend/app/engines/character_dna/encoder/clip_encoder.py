"""Character Encoder (Phase 14.5): image -> identity vector.

MVP encoder: deterministic pseudo-CLIP embedding. The character stem
(everything before a trailing `_vN` version marker) maps to a stable base
vector and each version adds a small jitter, so:

    same character, new version  ->  cosine ~0.99  (same identity)
    different characters          ->  cosine ~0.0

Swap `encode` for a real CLIP forward pass later; the interface is frozen.
"""

import hashlib
import re
from typing import Any

from app.utils import normalize_vector

EMBEDDING_DIM = 64
IDENTITY_JITTER = 0.08
VERSION_SUFFIX = re.compile(r"_v\d+$")


class CharacterEncoder:
    model = "clip-mock-v1"

    @property
    def model_name(self) -> str:
        return self.model

    async def encode(self, image: str) -> list[float]:
        stem = re.sub(r"\.[a-zA-Z0-9]+$", "", image or "")
        base_key = VERSION_SUFFIX.sub("", stem)
        base = self._hash_vector(base_key)
        delta = self._hash_vector(stem)
        return normalize_vector(
            [b + IDENTITY_JITTER * d for b, d in zip(base, delta)]
        )

    def describe(self) -> dict[str, Any]:
        return {"model": self.model, "dim": EMBEDDING_DIM}

    @staticmethod
    def _hash_vector(key: str) -> list[float]:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        stream = (digest * (EMBEDDING_DIM // len(digest) + 1))[:EMBEDDING_DIM]
        return normalize_vector([(b / 255.0) * 2 - 1 for b in stream])
