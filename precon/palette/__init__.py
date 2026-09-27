from precon._seed import hue_palette, seed_of, shade


def _from_roles(roles):
    """Expands the semantic role colours into a 16-colour palette."""
    outline = roles.get("outline") or "#07090d"
    shadow = roles.get("shadow") or shade(outline, 0.18)
    base = roles.get("base") or "#4cc2ff"
    highlight = roles.get("highlight") or shade(base, 0.45)
    accent = roles.get("accent") or highlight
    hair = roles.get("hair") or "#a16207"
    skin = roles.get("skin") or "#f4d58d"
    eyes = roles.get("eyes") or base
    metal = roles.get("metal") or "#94a3b8"

    return [
        outline,
        shade(shadow, -0.45),
        shadow,
        shade(base, -0.4),
        shade(base, -0.18),
        base,
        shade(base, 0.22),
        highlight,
        accent,
        shade(accent, -0.25),
        hair,
        shade(hair, -0.35),
        skin,
        shade(skin, -0.3),
        metal,
        eyes,
    ]


def reconstruct_palette(image, style=None):
    """Semantic palette reconstruction.

    A generation request ships ``image["palette"]`` (roles derived from the
    prompt); the palette is expanded to 16 colours. Without a prompt palette
    but with a seed, a deterministic hue ramp is used. The benchmark path
    (no palette, no seed) keeps the frozen baseline block.
    """

    roles = image.get("palette") if isinstance(image, dict) else None
    seed = seed_of(image)

    if isinstance(roles, dict) and roles:
        colors = _from_roles(roles)
        max_colors = 16
        source = "prompt"
        if style == "2d":
            # 2D requests keep gradient richness: mirror the ramp with
            # lightened steps instead of collapsing to 16 flat colours
            colors = colors + [shade(c, 0.28) for c in colors]
            max_colors = 32
            source = "prompt-2d"
        return {
            "max_colors": max_colors,
            "colors": colors,
            "semantic_roles": {
                "outline": roles.get("outline"),
                "shadow": roles.get("shadow"),
                "base": roles.get("base"),
                "highlight": roles.get("highlight"),
                "accent": roles.get("accent"),
                "hair": roles.get("hair"),
                "skin": roles.get("skin"),
                "eyes": roles.get("eyes"),
                "metal": roles.get("metal"),
            },
            "source": source
        }

    if seed is not None:
        colors = hue_palette(seed)
        return {
            "max_colors": 16,
            "colors": colors,
            "semantic_roles": {
                "outline": colors[0],
                "shadow": colors[2],
                "base": colors[5],
                "highlight": colors[7],
                "accent": colors[8],
                "hair": colors[10],
                "skin": colors[12],
                "eyes": colors[15],
                "metal": colors[14],
            },
            "source": "seed"
        }

    return {
        "max_colors": 16,
        "colors": [],
        "semantic_roles": {
            "outline": None,
            "shadow": None,
            "base": None,
            "highlight": None
        }
    }
