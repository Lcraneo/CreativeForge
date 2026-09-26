"""Asset Git (Phase 17.9): version lineage over character_versions.

    cat001: v1 base -> v2 armor -> v3 fire sword -> v4 animation polish

Every node knows its parent and its change set; the tree is rebuilt from
the persistence layer so restarts keep the full lineage.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CharacterVersion


async def version_lineage(db: AsyncSession, character_id: str) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(CharacterVersion)
            .where(CharacterVersion.character_id == character_id)
            .order_by(CharacterVersion.created_at)
        )
    ).scalars()
    return [
        {
            "id": row.id,
            "version": row.version,
            "parent": row.parent_version,
            "changes": row.changes or {},
            "asset_id": row.asset_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def build_tree(lineage: list[dict[str, Any]]) -> dict[str, Any]:
    by_version = {row["version"]: row for row in lineage}
    children: dict[str | None, list[str]] = {}
    for row in lineage:
        children.setdefault(row.get("parent"), []).append(row["version"])
    return {
        "versions": list(by_version),
        "children": children,
        "head": lineage[-1]["version"] if lineage else None,
    }
