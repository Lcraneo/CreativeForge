"""DNA API (Phase 14.12): create / query / similarity-search character DNA."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Asset, CharacterDna, CharacterEmbedding
from app.schemas.dna import (
    DnaCreateRequest,
    DnaCreateResponse,
    DnaResponse,
    DnaSearchRequest,
    DnaSearchResponse,
)
from app.services.dna_service import get_services

router = APIRouter()


@router.post("/create", response_model=DnaCreateResponse)
async def create_dna(data: DnaCreateRequest, db: AsyncSession = Depends(get_db)):
    services = get_services()
    await services.hydrate(db)

    row = await db.get(Asset, data.asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    asset: dict[str, Any] = row.metadata_json or {}

    existing = (asset.get("dna") or {}).get("character_id")
    if existing and services.dna.get(existing):
        return DnaCreateResponse(character_id=existing)

    dna = await services.dna.create(asset)
    await db.merge(
        CharacterDna(
            character_id=dna["character_id"],
            identity=dna["identity"],
            image_stem=dna.get("image_stem"),
        )
    )
    db.add(
        CharacterEmbedding(
            id=str(uuid.uuid4()),
            character_id=dna["character_id"],
            embedding=dna["embedding"]["vector"],
            model=dna["embedding"]["model"],
        )
    )
    await db.commit()
    return DnaCreateResponse(character_id=dna["character_id"])


@router.get("/{character_id}", response_model=DnaResponse)
async def get_dna(character_id: str, db: AsyncSession = Depends(get_db)):
    services = get_services()
    await services.hydrate(db)

    dna = services.dna.get(character_id)
    if dna is None:
        raise HTTPException(status_code=404, detail="character dna not found")
    record = services.dna.store.get(character_id)
    return DnaResponse(
        character_id=character_id,
        identity=dna.get("identity") or {},
        embedding={
            "model": (record and services.dna.encoder.model_name) or services.dna.encoder.model,
            "dim": len(record.vector) if record else 0,
        },
        versions=dna.get("versions") or [],
    )


@router.post("/search", response_model=DnaSearchResponse)
async def search(data: DnaSearchRequest, db: AsyncSession = Depends(get_db)):
    services = get_services()
    await services.hydrate(db)

    result = await services.dna.search(data.image)
    character = None
    if result.get("character"):
        record = result["character"]
        character = {
            "character_id": record.get("character_id"),
            "identity": record.get("identity") or {},
            "versions": record.get("versions") or [],
        }
    return DnaSearchResponse(
        match=result.get("match"),
        score=result.get("score", 0.0),
        is_same_character=result.get("is_same_character", False),
        character=character,
    )
