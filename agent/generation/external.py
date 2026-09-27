"""Build the image-generation prompt sent to a configured model API."""

# Per-style image prompt tails: the model must not be told "pixel art" when
# the user asked for a 2D / anime asset.
STYLE_PROMPT_TAILS = {
    "pixel": "pixel art game asset, transparent background, front-facing",
    "2d": "2d anime style game illustration, clean flat shading, full body, transparent background",
}


def build_image_prompt(goal, overrides=None, enhanced_prompt=None, style=None):
    """Compose a style-aware image prompt.

    Prefers an enhanced brief from the chat provider, falls back to the raw
    goal, and appends style-appropriate constraints.
    """

    if enhanced_prompt:
        base = enhanced_prompt
    elif goal:
        base = goal
    else:
        base = "a game character sprite"

    style_key = style or (overrides or {}).get("style") or "pixel"
    parts = [base, STYLE_PROMPT_TAILS.get(style_key, STYLE_PROMPT_TAILS["pixel"])]
    if isinstance(overrides, dict):
        requested = overrides.get("style")
        if requested:
            parts.append("style: " + str(requested))
    return ", ".join(parts)
