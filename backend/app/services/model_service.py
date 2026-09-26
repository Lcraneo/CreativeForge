"""Model service (Phase 20.16): serving layer over the foundation models.

    dna/embed       image -> DNA vector through the production encoder
                    (heavy inference: routed through the GPU queue)
    quality/check   asset -> consistency / game-ready scores
    motion/analyze  asset -> per-clip motion semantics
    train           asset library -> training run + registry artifact

The production artifact is loaded per call (cheap DB read), so promoting a
new model version takes effect on the next request — deployment without
code change.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.foundation.animation_library import describe, resolve_action
from app.engines.foundation.quality_model import assess_asset
from app.engines.foundation.training.encoder import FEATURE_DIM, HybridDNAEncoder
from app.engines.foundation.training.pipeline import run_training_pipeline
from app.models import Asset
from app.models.training import ModelArtifact, TrainingRun
from app.runtime.tiers import GpuQueue


class ModelService:
    def __init__(self):
        self.encoder = HybridDNAEncoder(dim=FEATURE_DIM)
        self.gpu = GpuQueue()

    # -- dna embedding (GPU tier) ------------------------------------------

    async def embed(
        self, image: str, artifact: ModelArtifact | None = None
    ) -> dict[str, Any]:
        weights = (artifact.weights or {}).get("scale") if artifact else None
        label = (
            f"{artifact.name}@v{artifact.version}"
            if artifact
            else f"{self.encoder.model}@untrained"
        )

        async def infer() -> dict[str, Any]:
            return self.encoder.embed(image, scale=weights)

        out = await self.gpu.submit(infer)
        result = out["result"]
        return {
            "image": image,
            "vector": result["vector"],
            "dim": result["dim"],
            "model": label,
            "tier": "gpu",
            "gpu": {"queued_ms": out["queued_ms"], "run_ms": out["run_ms"]},
        }

    # -- quality / motion ----------------------------------------------------

    async def quality_check(self, asset: dict[str, Any]) -> dict[str, Any]:
        checks = assess_asset(asset)
        booleans = [v for v in checks.values() if isinstance(v, bool)]
        game_ready = round(sum(booleans) / len(booleans), 4) if booleans else None
        return {"scores": checks, "game_ready": game_ready}

    async def motion_analyze(self, asset: dict[str, Any]) -> dict[str, Any]:
        clips = (asset.get("animation") or {}).get("clips") or []
        results = []
        for clip in clips:
            name = str(clip.get("name") or "")
            action = resolve_action([name, name.split("_")[0]])
            semantics = describe(action) or {}
            results.append(
                {
                    "name": name,
                    "action": action,
                    "semantic": semantics.get("semantic"),
                    "speed": semantics.get("speed"),
                    "weapon": semantics.get("weapon"),
                    "difficulty": semantics.get("difficulty"),
                    "fps": clip.get("fps"),
                    "frames": clip.get("frames"),
                }
            )
        return {"clips": results, "tier": "gpu"}

    # -- training ------------------------------------------------------------

    async def train(
        self, db: AsyncSession, name: str = "dna_encoder"
    ) -> dict[str, Any]:
        rows = (await db.execute(select(Asset))).scalars().all()
        assets = [row.metadata_json or {} for row in rows]
        report = await run_training_pipeline(assets, name=name, session=db)
        db.add(
            TrainingRun(
                id=str(uuid.uuid4()),
                name=name,
                status="completed",
                report=report,
                artifact_id=(report.get("artifact") or {}).get("id"),
            )
        )
        await db.commit()
        return report


_model_service: ModelService | None = None


def get_model_service() -> ModelService:
    global _model_service
    if _model_service is None:
        _model_service = ModelService()
    return _model_service
