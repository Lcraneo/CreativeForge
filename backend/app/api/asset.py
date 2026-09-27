"""Asset API (Phase 11.11 -> 18 -> 21): create / list / inspect / export.

`create` runs the Phase 16-17 agent runtime; `export` (Phase 18.10)
re-exports an existing CreativeAsset to another engine through GImport;
`export.zip` (Phase 21) downloads the engine resource tree as a real
archive (DNA.json / skill.json / textures / spriteframes / anims / prefab).
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Asset
from app.schemas.asset import (
    AssetCreateRequest,
    AssetCreateResponse,
    AssetDetail,
    AssetSummary,
    ExportRequest,
    ExportResponse,
)
from app.services.asset_service import create_asset
from app.services.export_service import (
    content_disposition,
    package_export_zip,
    run_export,
)
from app.services.image_service import (
    attach_image_url,
    normalize_view,
    render_asset_sheet_image,
    render_asset_view_image,
    stored_render,
)

router = APIRouter()


@router.post("/create", response_model=AssetCreateResponse)
async def create(data: AssetCreateRequest, db: AsyncSession = Depends(get_db)):
    result = await create_asset(
        data.prompt,
        db,
        engine=data.engine,
        review=data.review,
        user_id=data.user_id,
        provider=data.provider,
        model=data.model,
    )
    return AssetCreateResponse(
        task_id=result["task_id"],
        status=result["status"],
        plan=result["plan"],
        result=result["result"],
        asset_id=result.get("asset_id"),
        review=result.get("review"),
    )


@router.post("/export", response_model=ExportResponse)
async def export_asset(data: ExportRequest, db: AsyncSession = Depends(get_db)):
    row = await db.get(Asset, data.asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")

    exported, engine_target = await run_export(row, data.engine)
    await db.commit()

    resources = exported["engine"]["resources"]
    return ExportResponse(
        asset_id=exported["id"],
        engine=resources["engine"],
        root=resources["root"],
        files=sorted(resources["files"]),
        quality=resources["quality"],
    )


@router.get("/{asset_id}/export.zip")
async def export_zip(
    asset_id: str, engine: str | None = None, db: AsyncSession = Depends(get_db)
):
    """Phase 21: download the exported engine package as a zip archive."""
    row = await db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")

    exported, engine_target = await run_export(row, engine)
    await db.commit()

    payload, filename = package_export_zip(exported, engine_target)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/{asset_id}/image.png")
async def asset_image(
    asset_id: str,
    view: str = "front",
    size: int = 512,
    db: AsyncSession = Depends(get_db),
):
    """2D character artwork in a single orthographic view (front/side/top)."""
    row = await db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")

    metadata = dict(row.metadata_json or {})
    view_name = normalize_view(view)
    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-Image-Source": "artgen",
        "X-Image-Style": "2d",
        "X-Image-View": view_name,
    }

    # a hosted image API may have produced the original (front) render
    if view_name == "front":
        stored = stored_render(metadata)
        if stored is not None:
            payload, mime = stored
            content = metadata.get("content") or {}
            headers["X-Image-Source"] = "api"
            headers["X-Image-Provider"] = str(content.get("image_provider") or "")
            headers["X-Image-Model"] = str(content.get("image_model") or "")
            return Response(content=payload, media_type=mime, headers=headers)

    payload = render_asset_view_image(metadata, view=view_name, size=size)
    content = metadata.get("content") or {}
    headers["X-Image-Model"] = str(content.get("image_model") or "artgen-2d")
    headers["X-Image-Provider"] = str(content.get("image_provider") or "builtin")
    return Response(content=payload, media_type="image/png", headers=headers)


@router.get("/{asset_id}/views.png")
async def asset_views(
    asset_id: str, size: int = 512, gap: int = 24, db: AsyncSession = Depends(get_db)
):
    """Three-view character sheet (front | side | top) as one PNG."""
    row = await db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")

    payload = render_asset_sheet_image(dict(row.metadata_json or {}), size=size, gap=gap)
    return Response(
        content=payload,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Image-Source": "artgen",
            "X-Image-Style": "2d",
            "X-Image-View": "front,side,top",
        },
    )


@router.get("", response_model=list[AssetSummary])
async def list_assets(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(Asset).order_by(Asset.created_at.desc()).limit(limit))
    ).scalars()
    return [
        AssetSummary(
            id=row.id,
            name=row.name,
            asset_type=row.asset_type or "character",
            status=row.status or "created",
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{asset_id}", response_model=AssetDetail)
async def get_asset(asset_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    metadata = attach_image_url(dict(row.metadata_json or {}), asset_id)
    return AssetDetail(
        id=row.id,
        name=row.name,
        asset_type=row.asset_type or "character",
        status=row.status or "created",
        created_at=row.created_at,
        project_id=row.project_id or "default",
        metadata_json=metadata,
    )
