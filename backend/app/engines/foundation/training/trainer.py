"""Contrastive trainer (Phase 20.5 / 五): make distance(A, A) < distance(A, B).

MVP projection head: a learned diagonal re-weighting `s` over backbone
features (the full-matrix head plugs in behind the same `fit` interface).
Training is real gradient descent on the contrastive objective —
deterministic end to end (no RNG), so runs are reproducible and tests stable:

    L = sum_pos (1 - cos)^2 + sum_neg max(0, margin - (1 - cos))^2

Positive pairs pull together; negative pairs push apart until the margin
holds. Raw backbone features carry nuisance dimensions (view noise), so
training measurably sharpens identity separation (see evaluation.py).
"""

from typing import Any

from app.utils import normalize_vector

POSITIVE, NEGATIVE = 1, 0


class ContrastiveTrainer:
    def __init__(
        self,
        dim: int,
        margin: float = 0.6,
        lr: float = 0.15,
        steps: int = 300,
        min_scale: float = 0.05,
        max_scale: float = 20.0,
    ):
        self.dim = dim
        self.margin = margin
        self.lr = lr
        self.steps = steps
        self.min_scale = min_scale
        self.max_scale = max_scale

    # -- forward ------------------------------------------------------------

    def _project(self, row: list[float], scale: list[float]) -> tuple[list[float], float]:
        y = [s * x for s, x in zip(scale, row)]
        norm = math_norm(y)
        return [v / norm for v in y], norm

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def _pair_loss(self, cos: float, label: int) -> float:
        distance = 1.0 - cos
        if label == POSITIVE:
            return distance * distance
        violated = max(0.0, self.margin - distance)
        return violated * violated

    # -- training loop --------------------------------------------------------

    def fit(
        self, rows: list[list[float]], pairs: list[tuple[int, int, int]]
    ) -> dict[str, Any]:
        scale = [1.0] * self.dim
        loss_first = 0.0
        loss_last = 0.0

        for step in range(self.steps + 1):
            projected = []
            norms = []
            for row in rows:
                y, norm = self._project(row, scale)
                projected.append(y)
                norms.append(norm)

            grad = [0.0] * self.dim
            loss = 0.0
            for i, j, label in pairs:
                yi, yj = projected[i], projected[j]
                cos = self._cosine(yi, yj)
                loss += self._pair_loss(cos, label)

                distance = 1.0 - cos
                if label == POSITIVE:
                    dloss_dcos = -2.0 * distance
                elif distance < self.margin:
                    dloss_dcos = 2.0 * (self.margin - distance)
                else:
                    continue  # margin satisfied: no gradient

                for target, other in ((i, j), (j, i)):
                    yt, yo = projected[target], projected[other]
                    # dL/dŷ_target = dL/dcos * ŷ_other
                    d_hat = [dloss_dcos * v for v in yo]
                    dot = sum(g * v for g, v in zip(d_hat, yt))
                    # chain through normalization: dL/dy = (dL/dŷ - (dL/dŷ·ŷ)ŷ)/||y||
                    row_input = rows[target]
                    norm = norms[target] or 1.0
                    for k in range(self.dim):
                        d_y = (d_hat[k] - dot * yt[k]) / norm
                        grad[k] += d_y * row_input[k]

            if step == 0:
                loss_first = loss
            if step == self.steps:
                loss_last = loss
                break
            scale = [
                min(self.max_scale, max(self.min_scale, s - self.lr * g))
                for s, g in zip(scale, grad)
            ]

        return {
            "scale": [round(s, 6) for s in scale],
            "steps": self.steps,
            "lr": self.lr,
            "margin": self.margin,
            "loss_before": round(loss_first, 6),
            "loss_after": round(loss_last, 6),
            "pairs": len(pairs),
        }


def math_norm(values: list[float]) -> float:
    return sum(v * v for v in values) ** 0.5


def project_rows(
    rows: list[list[float]], scale: list[float] | None = None
) -> list[list[float]]:
    """Apply the projection head outside training (deployment path)."""
    if not scale:
        return [normalize_vector(row) for row in rows]
    return [
        normalize_vector([s * x for s, x in zip(scale, row)]) for row in rows
    ]
