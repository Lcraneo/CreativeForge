"""Game Asset Intelligence Dataset (Phase 20.2-6).

Not an image pile — per character: structure + motion + engine info
(spec 三), mined into contrastive identity pairs (spec 五):

    positive  same character, different image / view    label 1
    negative  different characters                      label 0

Views simulate the "different pose / angle / outfit" axis deterministically;
augmented views share the identity stem but add nuisance noise, which is
what the projection head learns to see through.
"""

from itertools import combinations
from typing import Any

from app.engines.foundation.training.encoder import VIEW_SALTS, image_stem


def _engine_targets(asset: dict[str, Any]) -> list[str]:
    target = (asset.get("engine") or {}).get("target")
    return [target] if target else []


def character_record(asset: dict[str, Any]) -> dict[str, Any]:
    """Spec 三 per-character folder, expressed as JSON:
    metadata.json / skeleton.json / animation/ / engine/."""
    dna = asset.get("dna") or {}
    identity = dna.get("identity") or {}
    graph = (asset.get("content") or {}).get("graph") or {}
    clips = (asset.get("animation") or {}).get("clips") or []
    return {
        "character_id": dna.get("character_id"),
        "images": [dna.get("image_stem") or (asset.get("content") or {}).get("image")],
        "metadata": {
            "name": identity.get("name"),
            "species": identity.get("species"),
            "role": identity.get("role"),
            "style": identity.get("style"),
            "palette": identity.get("color") or [],
        },
        "skeleton": {
            "nodes": _count_nodes(graph),
        },
        "animation": [
            {"name": clip.get("name"), "fps": clip.get("fps"), "frames": clip.get("frames")}
            for clip in clips
        ],
        "engine": _engine_targets(asset),
    }


def _count_nodes(node: dict[str, Any]) -> int:
    return 1 + sum(_count_nodes(child) for child in node.get("children", []))


def import_passed(asset: dict[str, Any]) -> bool:
    """Quality filter signal (Phase 20.15 preprocess): `quality.import` is
    the engine manifest score (1.0 = complete). Missing means unmeasured
    and keeps the sample; an explicit incomplete manifest drops it."""
    score = (asset.get("quality") or {}).get("import")
    if score is None:
        return True
    return isinstance(score, (int, float)) and score >= 1.0


def build_dataset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    characters: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for asset in assets:
        dna = asset.get("dna") or {}
        character_id = dna.get("character_id")
        image = dna.get("image_stem") or (asset.get("content") or {}).get("image")
        if not character_id or not image:
            continue

        record = characters.get(character_id)
        if record is None:
            record = character_record(asset)
            record["images"] = []
            characters[character_id] = record
        stem = image_stem(image)
        if stem not in record["images"]:
            record["images"].append(stem)

        for view in VIEW_SALTS:
            rows.append(
                {
                    "character_id": character_id,
                    "image": stem,
                    "view": view,
                    "quality_ok": import_passed(asset),
                }
            )

    usable = [row for row in rows if row["quality_ok"]]

    positive: list[tuple[int, int]] = []
    negative: list[tuple[int, int]] = []
    by_index = [row["character_id"] for row in usable]
    for i, j in combinations(range(len(usable)), 2):
        if by_index[i] == by_index[j]:
            positive.append((i, j))
        else:
            negative.append((i, j))

    return {
        "characters": list(characters.values()),
        "rows": usable,
        "dropped_rows": len(rows) - len(usable),
        "positive_pairs": positive,
        "negative_pairs": negative,
        "stats": {
            "characters": len(characters),
            "images": len({(row["character_id"], row["image"]) for row in usable}),
            "views": len(VIEW_SALTS),
            "rows": len(usable),
            "positive_pairs": len(positive),
            "negative_pairs": len(negative),
        },
    }


def dataset_manifest(dataset: dict[str, Any]) -> dict[str, Any]:
    """Spec 三 directory layout as an exportable manifest:
    CreativeForge Dataset / characters / <id> / {images, metadata, skeleton,
    animation, engine}."""
    return {
        "format": "creativeforge-dataset/1",
        "characters": dataset["characters"],
        "stats": dataset["stats"],
    }
