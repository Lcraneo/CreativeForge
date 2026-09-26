"""Quality Model (Phase 19.12-13): consistency assessment.

Not a trained model yet — a deterministic scorer over the same signals a
future similarity model would learn:

    appearance  palette overlap between versions
    structure   body proportion deviation
    style       style-name match

    similarity = weighted(appearance .5 / structure .3 / style .2)
"""

from typing import Any

WEIGHTS = {"appearance": 0.5, "structure": 0.3, "style": 0.2}


def _palette_overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    shared = len(set(a) & set(b))
    union = len(set(a) | set(b))
    return shared / union if union else 0.0


def _structure_deviation(a: dict[str, Any], b: dict[str, Any]) -> float:
    ha = (a.get("structure") or {}).get("height_ratio") or 1.0
    hb = (b.get("structure") or {}).get("height_ratio") or 1.0
    deviation = abs(ha - hb) / max(ha, hb, 1e-6)
    return max(0.0, 1.0 - deviation * 2)


def assess_identity(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """old/new: DNA records with `identity` + optional `profile`."""
    old_profile = old.get("profile") or {}
    new_profile = new.get("profile") or {}

    appearance = _palette_overlap(
        old_profile.get("palette") or (old.get("identity") or {}).get("color") or [],
        new_profile.get("palette") or (new.get("identity") or {}).get("color") or [],
    )
    structure = _structure_deviation(old_profile, new_profile)
    style = 1.0 if (old_profile.get("style") or {}).get("name") == (
        new_profile.get("style") or {}
    ).get("name") else 0.0

    overall = (
        WEIGHTS["appearance"] * appearance
        + WEIGHTS["structure"] * structure
        + WEIGHTS["style"] * style
    )
    return {
        "appearance": round(appearance, 4),
        "structure": round(structure, 4),
        "style": round(style, 4),
        "similarity": round(overall, 4),
    }


def assess_asset(asset: dict[str, Any]) -> dict[str, Any]:
    """Single-asset quality snapshot for dashboards (Phase 18.7)."""
    quality = asset.get("quality") or {}
    animation = asset.get("animation") or {}
    identity = asset.get("dna") or {}
    return {
        "identity": (identity.get("identity") or {}).get("species") is not None,
        "structural": bool((asset.get("content") or {}).get("layers")),
        "style": (asset.get("style") or {}).get("name"),
        "segmentation": quality.get("segmentation_score"),
        "motion_residual": (animation.get("motion") or {}).get("max_root_residual"),
        "import": quality.get("import"),
    }
