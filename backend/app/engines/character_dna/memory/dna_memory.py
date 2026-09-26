"""DNA Memory (Phase 14): character_id -> DNA record cache.

The database (`character_dnas`) is the source of truth; this keeps hot
records in-process for the agent pipeline.
"""

from typing import Any


class DNAMemory:
    def __init__(self):
        self.records: dict[str, dict[str, Any]] = {}

    def save(self, dna: dict[str, Any]) -> None:
        self.records[dna["character_id"]] = dna

    def get(self, character_id: str) -> dict[str, Any] | None:
        return self.records.get(character_id)

    def find_by_stem(self, stem: str) -> dict[str, Any] | None:
        for dna in self.records.values():
            if dna.get("image_stem") == stem:
                return dna
        return None

    def load(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.save(row)
