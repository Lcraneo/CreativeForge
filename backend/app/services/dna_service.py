"""Service container: shared DNA engine instance across requests.

On first use the container hydrates the in-process DNA memory / vector
store / version graph from PostgreSQL, so a restart keeps character
identity (Phase 14: Character Memory is durable).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.engines.character_dna.service import CharacterDNAService
from app.models import CharacterDna, CharacterEmbedding, CharacterVersion


class ServiceContainer:
    def __init__(self):
        self.dna = CharacterDNAService(threshold=settings.DNA_MATCH_THRESHOLD)
        self._hydrated = False

    async def hydrate(self, db: AsyncSession) -> None:
        if self._hydrated:
            return
        for row in (await db.execute(select(CharacterDna))).scalars():
            self.dna.memory.save(
                {
                    "character_id": row.character_id,
                    "identity": row.identity or {},
                    "image_stem": row.image_stem,
                    "embedding": {"vector": [], "model": ""},
                    "versions": [],
                }
            )
        for row in (await db.execute(select(CharacterEmbedding))).scalars():
            self.dna.store.upsert(row.character_id, row.embedding or [], {"model": row.model})
        rows = (
            await db.execute(select(CharacterVersion).order_by(CharacterVersion.created_at))
        ).scalars()
        for row in rows:
            self.dna.versions.load(
                [
                    {
                        "id": row.id,
                        "character_id": row.character_id,
                        "version": row.version,
                        "parent_version": row.parent_version,
                        "changes": row.changes or {},
                        "asset_id": row.asset_id,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                ]
            )
        self._hydrated = True


_services: ServiceContainer | None = None


def get_services() -> ServiceContainer:
    global _services
    if _services is None:
        _services = ServiceContainer()
    return _services
