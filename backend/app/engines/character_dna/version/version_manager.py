"""Version manager (Phase 14.9 / 14.10): characters evolve, never overwrite.

    Cat Warrior
        |- v1 base
        |- v2 fire sword
        \\- v3 mecha armor

Every modification records its change type so the agent understands it as
an edit, not a regeneration.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class VersionManager:
    def __init__(self):
        self.versions: dict[str, list[dict[str, Any]]] = {}

    def next_version(self, character_id: str) -> str:
        return f"v{len(self.versions.get(character_id, [])) + 1}"

    def create_version(
        self,
        character_id: str,
        changes: dict[str, Any],
        asset_id: str | None = None,
        parent_version: str | None = None,
    ) -> dict[str, Any]:
        existing = self.versions.setdefault(character_id, [])
        if parent_version is None and existing:
            parent_version = existing[-1]["version"]
        record = {
            "id": str(uuid4()),
            "character_id": character_id,
            "version": self.next_version(character_id),
            "parent_version": parent_version,
            "changes": changes or {},
            "asset_id": asset_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        existing.append(record)
        return record

    def lineage(self, character_id: str) -> list[dict[str, Any]]:
        return list(self.versions.get(character_id, []))

    def load(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.versions.setdefault(row["character_id"], []).append(row)
