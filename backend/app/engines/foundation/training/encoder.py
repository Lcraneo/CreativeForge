"""Hybrid DNA encoder (Phase 20.7-8): DINOv2 + CLIP -> projection head.

The spec's target architecture:

    Character Image
        |
        +--> DINOv2 branch (structure / identity)
        |
        +--> CLIP branch   (style / semantics)
        |
        +--> concat -> Projection Head -> DNA vector

MVP: both backbones are deterministic hash stand-ins. Raw backbone
features mix identity-bearing dimensions with nuisance dimensions (view /
augmentation noise), exactly the property the contrastive projection head
learns to exploit (Phase 20.15):

    dims  0-31  identity block   dino + clip, stable per character stem
    dims 32-63  nuisance block   per-image/view augmentation noise

Swap the hash branches for real forward passes; the interface is frozen.
"""

import re
from typing import Any

from app.utils import normalize_vector

BRANCH_DIM = 32
FEATURE_DIM = 2 * BRANCH_DIM
IDENTITY_JITTER = 0.08
VERSION_SUFFIX = re.compile(r"_v\d+$")
EXT_SUFFIX = re.compile(r"\.[a-zA-Z0-9]+$")

# Augmentation views (Phase 20.5: same character, different pose / angle /
# outfit -> identity pair). The canonical view is what serving embeds.
VIEW_SALTS = ("canonical", "flip", "crop")


def image_stem(image: str) -> str:
    return EXT_SUFFIX.sub("", image or "")


def base_stem(image: str) -> str:
    return VERSION_SUFFIX.sub("", image_stem(image))


def _hash_vector(key: str, dim: int) -> list[float]:
    import hashlib

    digest = hashlib.sha256(key.encode("utf-8")).digest()
    stream = (digest * (dim // len(digest) + 1))[:dim]
    return [(b / 255.0) * 2 - 1 for b in stream]


def _mix(*parts: tuple[list[float], float]) -> list[float]:
    out = [0.0] * len(parts[0][0])
    for vec, weight in parts:
        for i, value in enumerate(vec):
            out[i] += weight * value
    return out


def extract_features(image: str, view: str = VIEW_SALTS[0]) -> list[float]:
    """Backbone stand-in: identity + nuisance block per image/view."""
    stem = image_stem(image)
    base = base_stem(image)
    identity = _mix(
        (_hash_vector("dino:" + base, BRANCH_DIM), 1.0),
        (_hash_vector("dino:" + stem, BRANCH_DIM), IDENTITY_JITTER),
        (_hash_vector("clip:" + base, BRANCH_DIM), 1.0),
    )
    nuisance = _hash_vector(f"noise:{stem}@{view}", BRANCH_DIM)
    return normalize_vector(identity + nuisance)


class HybridDNAEncoder:
    """Feature extraction + learned projection -> deployed DNA vector."""

    model = "dna-encoder"

    def __init__(self, dim: int = FEATURE_DIM):
        self.dim = dim

    def embed(
        self, image: str, scale: list[float] | None = None
    ) -> dict[str, Any]:
        features = extract_features(image)
        vector = self.apply(features, scale)
        return {"vector": vector, "dim": len(vector)}

    def apply(
        self, features: list[float], scale: list[float] | None = None
    ) -> list[float]:
        if not scale or len(scale) != len(features):
            return normalize_vector(list(features))
        return normalize_vector([s * f for s, f in zip(scale, features)])

    def describe(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "dim": self.dim,
            "backbones": ["dino-mock", "clip-mock"],
            "projection": "learned-diagonal (Phase 20.15)",
        }
