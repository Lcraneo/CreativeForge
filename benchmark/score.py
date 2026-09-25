"""CreativeForge Score (Phase 9, section 十).

    CF Score = Pixel Quality + Animation Quality
             + Engine Compatibility + Agent Efficiency

Output plugs straight into the CreativeAsset Quality field (Phase 1):

    {"quality": {"pixel": .., "animation": .., "engine": .., "overall": ..}}

Weights: pixel and animation carry the self-developed-engine payload,
engine compatibility is the delivery gate, agent efficiency rewards the
autonomous layer.
"""

WEIGHTS = {
    "pixel": 0.30,
    "animation": 0.30,
    "engine": 0.25,
    "agent": 0.15
}


def cf_score(pixel, animation, engine, agent):
    """Weighted CF Score from the four benchmark section scores (0..1)."""
    weighted = (
        WEIGHTS["pixel"] * pixel
        + WEIGHTS["animation"] * animation
        + WEIGHTS["engine"] * engine
        + WEIGHTS["agent"] * agent
    )
    return {
        "weights": dict(WEIGHTS),
        "components": {
            "pixel": round(pixel, 4),
            "animation": round(animation, 4),
            "engine": round(engine, 4),
            "agent": round(agent, 4)
        },
        "overall": round(weighted, 4)
    }


def quality_block(cf):
    """Render a CF result as the CreativeAsset quality field."""
    components = cf["components"]
    return {
        "pixel": {"overall": components["pixel"]},
        "animation": {"overall": components["animation"]},
        "engine": {"overall": components["engine"]},
        "overall": cf["overall"]
    }
