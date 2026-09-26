"""Pipeline persistence (shared by the linear service and the Agent Runtime).

Writes the final CreativeAsset and every engine by-product: asset row,
layers, graph nodes, DNA + embeddings + versions, animation clips/events,
task record.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnimationClip,
    AnimationEvent,
    Asset,
    AssetLayer,
    AssetNode,
    CharacterDna,
    CharacterEmbedding,
    CharacterVersion,
    Task,
)
from app.services.image_service import attach_image_url


def _flatten_graph(node: dict, parent_id: str | None = None, rows: list | None = None):
    rows = [] if rows is None else rows
    rows.append({"id": node["id"], "parent_id": parent_id, "type": node["type"]})
    for child in node.get("children", []):
        _flatten_graph(child, node["id"], rows)
    return rows


async def persist_pipeline(
    db: AsyncSession,
    context: dict[str, Any],
    task_id: str,
    plan: dict,
    results: dict,
) -> str:
    asset = context.get("asset") or {}
    asset_id = str(uuid.uuid4())
    asset["id"] = asset_id
    attach_image_url(asset, asset_id)

    name = (asset.get("identity") or {}).get("name") or "unnamed"
    db.add(
        Asset(
            id=asset_id,
            project_id="default",
            name=name,
            asset_type="character",
            status="ready",
            metadata_json=asset,
        )
    )

    for layer in (asset.get("content") or {}).get("layers", []):
        db.add(
            AssetLayer(
                id=str(uuid.uuid4()),
                asset_id=asset_id,
                name=layer["name"],
                type=layer["type"],
                image_url=layer.get("image"),
                mask_url=layer.get("mask"),
                bbox=layer.get("bbox"),
                confidence=layer.get("confidence", 0.0),
            )
        )

    for node in _flatten_graph(
        (asset.get("content") or {}).get("graph") or {"id": "character", "type": "character"}
    ):
        db.add(
            AssetNode(
                id=f"{asset_id}:{node['id']}",
                asset_id=asset_id,
                parent_id=f"{asset_id}:{node['parent_id']}" if node["parent_id"] else None,
                type=node["type"],
            )
        )

    dna = context.get("dna")
    if dna:
        await db.merge(
            CharacterDna(
                character_id=dna["character_id"],
                identity=dna.get("identity") or {},
                image_stem=dna.get("image_stem"),
            )
        )
        vector = (dna.get("embedding") or {}).get("vector") or []
        if vector:
            db.add(
                CharacterEmbedding(
                    id=str(uuid.uuid4()),
                    character_id=dna["character_id"],
                    embedding=vector,
                    model=(dna.get("embedding") or {}).get("model") or "clip-mock-v1",
                )
            )
        existing = set(
            (
                await db.execute(
                    select(CharacterVersion.id).where(
                        CharacterVersion.character_id == dna["character_id"]
                    )
                )
            ).scalars()
        )
        for record in dna.get("version_records", []):
            if record["id"] in existing:
                continue
            created = record.get("created_at")
            db.add(
                CharacterVersion(
                    id=record["id"],
                    character_id=record["character_id"],
                    version=record.get("version") or "v1",
                    parent_version=record.get("parent_version"),
                    changes=record.get("changes") or {},
                    asset_id=asset_id,
                    created_at=datetime.fromisoformat(created) if created else None,
                )
            )

    character_id = (asset.get("dna") or {}).get("character_id")
    for clip in (asset.get("animation") or {}).get("clips", []):
        clip_id = str(uuid.uuid4())
        db.add(
            AnimationClip(
                id=clip_id,
                character_id=character_id,
                name=clip["name"],
                duration=clip["duration"],
                fps=clip["fps"],
                metadata_json=clip,
            )
        )
        for event in clip.get("events", []):
            db.add(
                AnimationEvent(
                    id=str(uuid.uuid4()),
                    animation_id=clip_id,
                    frame=event["frame"],
                    event_type=event["type"],
                    payload={"value": event.get("value"), "time": event.get("time")},
                )
            )

    db.add(Task(id=task_id, goal=plan["goal"], status="completed", plan=plan, result=results))
    await db.commit()
    return asset_id
