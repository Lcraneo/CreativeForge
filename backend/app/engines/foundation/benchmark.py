"""Game Creation Benchmark (Phase 23.13): our own evaluation system.

    Asset Score  identity consistency / completeness / style
    Game Score   runnable / interaction / performance
    Agent Score  task completion rate / self-repair usage / avg confidence

    CF Game Score = weighted(Asset .5 / Game .3 / Agent .2)
"""

from typing import Any

WEIGHTS = {"asset": 0.5, "game": 0.3, "agent": 0.2}


def _frame_count(clip: dict[str, Any]) -> int:
    frames = clip.get("frames")
    if isinstance(frames, list):
        return len(frames)
    if isinstance(frames, (int, float)):
        return int(frames)
    return 0


def asset_score(asset: dict[str, Any]) -> dict[str, Any]:
    dna = asset.get("dna") or {}
    similarity = dna.get("identity_similarity")
    identity = (
        round(float(similarity), 4)
        if isinstance(similarity, (int, float))
        else (1.0 if dna else 0.0)
    )

    layers = (asset.get("content") or {}).get("layers") or []
    clips = (asset.get("animation") or {}).get("clips") or []
    skills = (asset.get("combat") or {}).get("skills") or []
    engine_resources = (asset.get("engine") or {}).get("resources") or {}
    completeness = round(
        sum(bool(part) for part in (layers, clips, skills, engine_resources)) / 4,
        4,
    )

    quality = (engine_resources.get("quality") or {})
    runnable = quality.get("manifest_score")
    runnable = float(runnable) if isinstance(runnable, (int, float)) else 0.0
    interaction = 1.0 if skills and any(c.get("events") for c in clips) else 0.0
    frames_total = sum(_frame_count(c) for c in clips)
    performance = 1.0 if frames_total <= 64 else 0.8
    game = {
        "runnable": round(runnable, 4),
        "interaction": interaction,
        "performance": performance,
    }
    game_overall = round(sum(game.values()) / 3, 4)

    asset_overall = round(0.4 * identity + 0.4 * completeness + 0.2 * game_overall, 4)
    return {
        "asset": {"identity": identity, "completeness": completeness},
        "game": game,
        "overall": asset_overall,
    }


def agent_score(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    healed = sum(
        1
        for t in tasks
        if any(
            (s or {}).get("node") in ("self_evaluation",) or (s or {}).get("status") == "healed"
            for s in t.get("steps") or []
        )
    )
    confidences = [
        (s or {}).get("summary", {}).get("confidence")
        for t in tasks
        for s in t.get("steps") or []
        if isinstance((s or {}).get("summary"), dict)
        and isinstance(s["summary"].get("confidence"), (int, float))
    ]
    return {
        "total_tasks": total,
        "completed": completed,
        "completion_rate": round(completed / total, 4) if total else 0.0,
        "self_repaired_tasks": healed,
        "avg_confidence": (
            round(sum(confidences) / len(confidences), 4) if confidences else None
        ),
    }


def cf_score(scores: list[dict[str, Any]], agent: dict[str, Any]) -> float:
    """CF Game Score = weighted(Asset .5 / Game .3 / Agent .2)."""
    if scores:
        asset_mean = sum(
            0.5 * s["asset"]["identity"] + 0.5 * s["asset"]["completeness"]
            for s in scores
        ) / len(scores)
        game_mean = sum(
            0.4 * s["game"]["runnable"]
            + 0.4 * s["game"]["interaction"]
            + 0.2 * s["game"]["performance"]
            for s in scores
        ) / len(scores)
    else:
        asset_mean = game_mean = 0.0
    agent_overall = (
        agent["completion_rate"] * 0.7 + (agent["avg_confidence"] or 0.0) * 0.3
    )
    return round(
        WEIGHTS["asset"] * asset_mean
        + WEIGHTS["game"] * game_mean
        + WEIGHTS["agent"] * agent_overall,
        4,
    )
