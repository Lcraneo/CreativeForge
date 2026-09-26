"""Agent Memory System (Phase 16.12 / 17.8): production memory, not chat.

    Character Memory  -> the DNA service (character identity, embeddings)
    Asset Memory      -> generated assets (agent_tasks + assets tables)
    Version Memory    -> character version graphs
    User Preference   -> style / engine habits (persisted)
    Process Memory    -> tool execution experience (in-process stats)
"""

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentTask, Asset, UserPreference


class ProcessMemory:
    """Tool result cache + execution stats (Phase 17.12)."""

    def __init__(self):
        self.stats: dict[str, dict[str, Any]] = {}
        self._cache: dict[str, Any] = {}

    def record(self, tool: str, ms: float, ok: bool) -> None:
        entry = self.stats.setdefault(tool, {"runs": 0, "failures": 0, "total_ms": 0.0})
        entry["runs"] += 1
        entry["failures"] += 0 if ok else 1
        entry["total_ms"] = round(entry["total_ms"] + ms, 3)

    def get_cached(self, key: str) -> Any:
        return self._cache.get(key)

    def set_cached(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def describe(self) -> dict[str, Any]:
        return {
            tool: {
                "runs": entry["runs"],
                "failures": entry["failures"],
                "avg_ms": round(entry["total_ms"] / entry["runs"], 2) if entry["runs"] else 0.0,
            }
            for tool, entry in self.stats.items()
        }


class AgentMemory:
    def __init__(self):
        self.process = ProcessMemory()

    # -- user preference memory -------------------------------------------

    async def remember_preference(
        self, db: AsyncSession, user_id: str, key: str, value: Any
    ) -> None:
        row = (
            await db.execute(
                select(UserPreference).where(
                    UserPreference.user_id == user_id, UserPreference.key == key
                )
            )
        ).scalars().first()
        if row is None:
            db.add(
                UserPreference(
                    id=f"{user_id}:{key}", user_id=user_id, key=key, value={"value": value}
                )
            )
        else:
            row.value = {"value": value}
        await db.commit()

    async def recall_preferences(self, db: AsyncSession, user_id: str) -> dict[str, Any]:
        rows = (
            await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
        ).scalars()
        return {row.key: (row.value or {}).get("value") for row in rows}

    # -- asset memory -------------------------------------------------------

    async def recent_assets(self, db: AsyncSession, limit: int = 5) -> list[dict[str, Any]]:
        rows = (
            await db.execute(select(Asset).order_by(Asset.created_at.desc()).limit(limit))
        ).scalars()
        return [
            {"id": row.id, "name": row.name, "created_at": str(row.created_at)} for row in rows
        ]

    async def recent_tasks(self, db: AsyncSession, limit: int = 5) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
            )
        ).scalars()
        return [
            {"id": row.id, "goal": row.goal, "status": row.status, "asset_id": row.asset_id}
            for row in rows
        ]


def timed(record_to: ProcessMemory, tool: str):
    """Decorator helper context: measure one agent/tool execution."""

    class _Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc, tb):
            record_to.record(tool, (time.perf_counter() - self.start) * 1000, exc_type is None)
            return False

    return _Timer()
