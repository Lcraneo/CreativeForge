"""Training pipeline (Phase 20.15): the seven-step loop from the spec.

    Dataset -> Preprocess -> Embedding Extraction -> Contrastive Training
            -> Evaluation -> Model Registry -> Deployment

Deployment is the registry promotion at the end: the model service serves
whatever artifact is in `production` status, so a trained head reaches the
API without any code change.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.foundation.training.dataset import build_dataset, dataset_manifest
from app.engines.foundation.training.encoder import FEATURE_DIM, extract_features
from app.engines.foundation.training.evaluation import evaluate
from app.engines.foundation.training.trainer import POSITIVE, ContrastiveTrainer


def _preprocess(dataset: dict[str, Any]) -> dict[str, Any]:
    """Quality filter: drop samples whose engine import explicitly failed."""
    kept = [row for row in dataset["rows"] if row["quality_ok"]]
    dropped = len(dataset["rows"]) - len(kept)
    positives = [
        (i, j)
        for i, j in dataset["positive_pairs"]
        if i < len(kept) and j < len(kept)
    ]
    negatives = [
        (i, j)
        for i, j in dataset["negative_pairs"]
        if i < len(kept) and j < len(kept)
    ]
    return {
        "rows": kept,
        "positive_pairs": positives,
        "negative_pairs": negatives,
        "dropped": dropped,
    }


async def run_training_pipeline(
    assets: list[dict[str, Any]],
    *,
    name: str = "dna_encoder",
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    # 1. dataset: identity pairs over the asset library
    dataset = build_dataset(assets)

    # 2. preprocess: quality filter
    clean = _preprocess(dataset)
    rows = clean["rows"]
    character_ids = [row["character_id"] for row in rows]

    # 3. embedding extraction (backbone stand-ins)
    features = [extract_features(row["image"], row["view"]) for row in rows]
    pairs = [
        (i, j, POSITIVE) for i, j in clean["positive_pairs"]
    ] + [(i, j, 0) for i, j in clean["negative_pairs"]]

    # 4. contrastive training (deterministic gradient descent)
    trainer = ContrastiveTrainer(dim=FEATURE_DIM)
    training = trainer.fit(features, pairs)

    # 5. evaluation: before vs after
    metrics_before = evaluate(features, character_ids, pairs)
    metrics_after = evaluate(features, character_ids, pairs, scale=training["scale"])

    report: dict[str, Any] = {
        "name": name,
        "dataset": dataset_manifest(dataset),
        "preprocess": {
            "kept": len(rows),
            "dropped": clean["dropped"],
        },
        "training": {
            "steps": training["steps"],
            "lr": training["lr"],
            "margin": training["margin"],
            "pairs": training["pairs"],
            "loss_before": training["loss_before"],
            "loss_after": training["loss_after"],
        },
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "improved": metrics_after["margin"] > metrics_before["margin"],
    }

    # 6. model registry + 7. deployment (production promotion)
    if session is not None:
        from app.engines.foundation.training.registry import (
            artifact_dict,
            register_and_promote,
        )

        artifact = await register_and_promote(
            session,
            name=name,
            kind="dna_encoder",
            metrics={
                "before": metrics_before,
                "after": metrics_after,
                "loss_before": training["loss_before"],
                "loss_after": training["loss_after"],
            },
            config={
                "dim": FEATURE_DIM,
                "steps": training["steps"],
                "lr": training["lr"],
                "margin": training["margin"],
            },
            weights={"scale": training["scale"]},
        )
        report["artifact"] = artifact_dict(artifact)

    return report
