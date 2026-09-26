"""Game Creation Benchmark API (Phase 23.13): our own evaluation system."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.foundation.benchmark import agent_score, asset_score, cf_score
from app.models import AgentTask, Asset

router = APIRouter()


@router.post("/run")
async def run_benchmark(db: AsyncSession = Depends(get_db)):
    assets = (
        (await db.execute(select(Asset).order_by(Asset.created_at))).scalars().all()
    )
    tasks = (
        (await db.execute(select(AgentTask).order_by(AgentTask.created_at)))
        .scalars()
        .all()
    )

    scores = [asset_score(row.metadata_json or {}) for row in assets]
    agent = agent_score(
        [
            {
                "status": (t.status or "").lower(),
                "steps": t.steps or [],
            }
            for t in tasks
        ]
    )
    return {
        "assets": [
            {
                "asset_id": row.id,
                "name": row.name,
                "scores": score,
            }
            for row, score in zip(assets, scores)
        ],
        "agent": agent,
        "cf_score": cf_score(scores, agent),
    }
