"""Model API (Phase 20.16): training, registry, and model-serving endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.foundation.training.registry import artifact_dict, get_production, list_artifacts
from app.models import Asset
from app.models.training import TrainingRun
from app.runtime.tiers import TASK_TIERS
from app.schemas.models import (
    EmbedRequest,
    EmbedResponse,
    MotionAnalyzeRequest,
    MotionAnalyzeResponse,
    QualityCheckRequest,
    QualityCheckResponse,
    RegistryResponse,
    RunsResponse,
    TrainRequest,
    TrainResponse,
    TiersResponse,
)
from app.services.model_service import get_model_service

router = APIRouter()


@router.post("/train", response_model=TrainResponse)
async def train(data: TrainRequest, db: AsyncSession = Depends(get_db)):
    report = await get_model_service().train(db, name=data.name)
    return TrainResponse(report=report)


@router.get("/registry", response_model=RegistryResponse)
async def registry(name: str | None = None, db: AsyncSession = Depends(get_db)):
    artifacts = await list_artifacts(db, name)
    return RegistryResponse(artifacts=[artifact_dict(a) for a in artifacts])


@router.get("/runs", response_model=RunsResponse)
async def runs(db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(select(TrainingRun).order_by(TrainingRun.created_at)))
        .scalars()
        .all()
    )
    return RunsResponse(
        runs=[
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "artifact_id": row.artifact_id,
                "created_at": str(row.created_at),
            }
            for row in rows
        ]
    )


@router.post("/dna/embed", response_model=EmbedResponse)
async def embed(data: EmbedRequest, db: AsyncSession = Depends(get_db)):
    artifact = await get_production(db, "dna_encoder")
    return await get_model_service().embed(data.image, artifact)


@router.post("/quality/check", response_model=QualityCheckResponse)
async def quality_check(data: QualityCheckRequest, db: AsyncSession = Depends(get_db)):
    row = await db.get(Asset, data.asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    result = await get_model_service().quality_check(row.metadata_json or {})
    return QualityCheckResponse(asset_id=data.asset_id, **result)


@router.post("/motion/analyze", response_model=MotionAnalyzeResponse)
async def motion_analyze(data: MotionAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    row = await db.get(Asset, data.asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    result = await get_model_service().motion_analyze(row.metadata_json or {})
    return MotionAnalyzeResponse(asset_id=data.asset_id, **result)


@router.get("/tiers", response_model=TiersResponse)
async def tiers():
    return TiersResponse(tiers=dict(TASK_TIERS))
