"""Retrieval evaluation (Phase 20.15 step 5): did training help?

Metrics over the identity dataset, computable before and after training:

    mean_positive_cos   same-character pair cosine (want high)
    mean_negative_cos   different-character pair cosine (want low)
    margin              positive - negative separation (want growing)
    retrieval_accuracy  nearest-neighbour hit rate @1 (want 1.0)
"""

from typing import Any

from app.engines.foundation.training.trainer import POSITIVE, project_rows


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def evaluate(
    rows: list[list[float]],
    character_ids: list[str],
    pairs: list[tuple[int, int, int]],
    scale: list[float] | None = None,
) -> dict[str, Any]:
    projected = project_rows(rows, scale)

    pos = [
        _cosine(projected[i], projected[j])
        for i, j, label in pairs
        if label == POSITIVE
    ]
    neg = [
        _cosine(projected[i], projected[j])
        for i, j, label in pairs
        if label != POSITIVE
    ]
    mean_pos = sum(pos) / len(pos) if pos else 0.0
    mean_neg = sum(neg) / len(neg) if neg else 0.0

    # nearest-neighbour retrieval @1: closest other row must share identity
    hits = 0
    for i, probe in enumerate(projected):
        best_score, best_hit = -2.0, False
        for j, candidate in enumerate(projected):
            if i == j:
                continue
            score = _cosine(probe, candidate)
            if score > best_score:
                best_score, best_hit = score, character_ids[j] == character_ids[i]
        hits += best_hit

    return {
        "mean_positive_cos": round(mean_pos, 4),
        "mean_negative_cos": round(mean_neg, 4),
        "margin": round(mean_pos - mean_neg, 4),
        "retrieval_accuracy": round(hits / len(projected), 4) if projected else 0.0,
    }
