"""Knowledge API (Phase 23.2-4): the Game Asset Knowledge Graph."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.foundation.knowledge import build_knowledge_graph
from app.models import Asset

router = APIRouter()


@router.get("/graph")
async def knowledge_graph(
    limit: int = Query(default=50, le=200), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(select(Asset).order_by(Asset.created_at.desc()).limit(limit))
    ).scalars().all()
    graph = build_knowledge_graph([row.metadata_json or {} for row in rows])
    payload = graph.to_dict()
    payload["assets_mined"] = len(rows)
    return payload
