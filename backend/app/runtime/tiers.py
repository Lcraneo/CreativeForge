"""Task tier routing (Phase 20.17): heavy GPU work vs light CPU work.

Cold/hot split from the spec:

    GPU  image generation / animation analysis / model inference
    CPU  graph queries / metadata processing / agent planning

Every executor step records its tier (visible in the task trace), and
`GpuQueue` is the stand-in for the GPU worker pool: heavy inference
serializes through one semaphore, light CPU work never enters it.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable

TASK_TIERS: dict[str, str] = {
    # heavy: model inference / generation / analysis
    "generate_asset": "gpu",
    "structure_asset": "gpu",   # vision analysis
    "create_dna": "gpu",        # embedding inference
    "motion_align": "gpu",      # animation analysis
    "quality_check": "gpu",     # quality model inference
    "model_inference": "gpu",
    # light: planning / metadata / graph
    "memory": "cpu",
    "combat": "cpu",
    "gimport": "cpu",
    "modify_style": "cpu",  # palette/metadata edit, no model inference
    "create_logic": "cpu",  # deterministic logic generation
    "simulate": "cpu",      # balance checks, no model inference
}


def tier_for(node: str) -> str:
    return TASK_TIERS.get(node, "cpu")


class GpuQueue:
    """Single-worker GPU pool stand-in: `submit` serializes heavy calls and
    reports queue/run timings; swap for Celery/Ray workers later."""

    def __init__(self, workers: int = 1):
        self._semaphore = asyncio.Semaphore(workers)
        self._submitted = 0
        self._completed = 0
        self._total_run_ms = 0.0

    async def submit(
        self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        self._submitted += 1
        queued_at = time.perf_counter()
        async with self._semaphore:
            queued_ms = round((time.perf_counter() - queued_at) * 1000, 2)
            started = time.perf_counter()
            result = await fn(*args, **kwargs)
            run_ms = round((time.perf_counter() - started) * 1000, 2)
        self._completed += 1
        self._total_run_ms += run_ms
        return {"result": result, "queued_ms": queued_ms, "run_ms": run_ms}

    def stats(self) -> dict[str, Any]:
        return {
            "submitted": self._submitted,
            "completed": self._completed,
            "total_run_ms": round(self._total_run_ms, 2),
        }
