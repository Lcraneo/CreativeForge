"""Vector store (Phase 14.8).

MVP: in-memory store with cosine search — the Character Memory the DNA
engine queries (`search(vector, top_k=5)`). The service layer hydrates it
from `character_embeddings` on demand; swap for Milvus / Chroma later.
"""

from dataclasses import dataclass, field
from typing import Any

from app.utils import cosine_similarity


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    def __init__(self):
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        self.records[id] = VectorRecord(id=id, vector=list(vector), metadata=metadata or {})

    def get(self, id: str) -> VectorRecord | None:
        return self.records.get(id)

    def search(self, vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        scored = [
            {"id": record.id, "score": round(cosine_similarity(vector, record.vector), 4)}
            for record in self.records.values()
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def load(self, rows: list[dict[str, Any]]) -> None:
        """Hydrate from persisted `(character_id, embedding, metadata)` rows."""
        for row in rows:
            self.upsert(row["character_id"], row["embedding"], row.get("metadata"))
