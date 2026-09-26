"""Model Registry (Phase 20.15-16): versioned artifacts + promotion.

    staged -> production -> archived

Every training run registers an artifact (metrics + config + weights);
promoting a version archives the previous production one. The model
service (Phase 20.16) serves through the production artifact, so
deployment is a registry status change — no code path forks.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import ModelArtifact

KINDS = (
    "dna_encoder",
    "quality_model",
    "motion_model",
    "lora_style",
    "lora_format",
    "lora_identity",
)


async def next_version(session: AsyncSession, name: str) -> int:
    rows = await session.execute(
        select(ModelArtifact.version).where(ModelArtifact.name == name)
    )
    return max((v for (v,) in rows.all()), default=0) + 1


async def register(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    metrics: dict[str, Any],
    config: dict[str, Any],
    weights: dict[str, Any],
) -> ModelArtifact:
    version = await next_version(session, name)
    artifact = ModelArtifact(
        id=str(uuid.uuid4()),
        name=name,
        kind=kind,
        version=version,
        status="staged",
        metrics=metrics,
        config=config,
        weights=weights,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def promote(session: AsyncSession, artifact: ModelArtifact) -> ModelArtifact:
    current = await get_production(session, artifact.name)
    if current is not None and current.id != artifact.id:
        current.status = "archived"
    artifact.status = "production"
    await session.flush()
    return artifact


async def register_and_promote(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    metrics: dict[str, Any],
    config: dict[str, Any],
    weights: dict[str, Any],
) -> ModelArtifact:
    artifact = await register(
        session, name=name, kind=kind, metrics=metrics, config=config, weights=weights
    )
    return await promote(session, artifact)


async def get_production(session: AsyncSession, name: str) -> ModelArtifact | None:
    rows = await session.execute(
        select(ModelArtifact)
        .where(ModelArtifact.name == name, ModelArtifact.status == "production")
        .order_by(ModelArtifact.version.desc())
    )
    return rows.scalars().first()


async def list_artifacts(
    session: AsyncSession, name: str | None = None
) -> list[ModelArtifact]:
    query = select(ModelArtifact).order_by(
        ModelArtifact.name, ModelArtifact.version.desc()
    )
    if name:
        query = query.where(ModelArtifact.name == name)
    rows = await session.execute(query)
    return list(rows.scalars().all())


def artifact_dict(artifact: ModelArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "name": artifact.name,
        "kind": artifact.kind,
        "version": artifact.version,
        "status": artifact.status,
        "metrics": artifact.metrics or {},
        "config": artifact.config or {},
    }
