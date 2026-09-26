"""Similarity retrieval (Phase 14.7): is this the same character?

    new_embedding VS database embeddings -> cosine similarity
    score > threshold -> same character
"""

from typing import Any

from app.engines.character_dna.vector.store import VectorStore
from app.utils import cosine_similarity

__all__ = ["cosine_similarity", "DNAResolver"]


class DNAResolver:
    def __init__(self, store: VectorStore, threshold: float = 0.85):
        self.store = store
        self.threshold = threshold

    async def search(self, vector: list[float]) -> dict[str, Any]:
        hits = self.store.search(vector, top_k=1)
        if not hits:
            return {"match": None, "score": 0.0, "is_same_character": False}
        best = hits[0]
        return {
            "match": best["id"],
            "score": best["score"],
            "is_same_character": best["score"] > self.threshold,
        }
