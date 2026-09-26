"""Small helpers shared by adapters and engines.

The MVP engines are deterministic: instead of calling heavyweight models
they derive stable pseudo-random values from string hashes, so the same
input always produces the same output (reproducible demos, stable tests).
"""

import hashlib
import math
import re
import unicodedata


def stable_hash(key: str) -> int:
    """Deterministic 64-bit positive hash of a string."""
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def slugify(text: str, fallback: str = "asset") -> str:
    """ASCII/CJK-safe slug: keep CJK characters, strip unsafe separators."""
    text = unicodedata.normalize("NFKC", text or "").strip()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text.lower() or fallback


def normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
