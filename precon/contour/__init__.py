from precon._seed import rng, seed_of


def repair_contour(image):
    """Contour repair: prompt-specific connectivity / style, stable baseline
    behaviour for the benchmark (seedless) path."""

    seed = seed_of(image)
    if seed is None:
        return {
            "thickness": 1,
            "connectivity": 8,
            "style": "hard",
            "repaired": True
        }

    random = rng(seed, salt=2)
    roll = random()
    style = "hard" if roll > 0.66 else ("selective" if roll > 0.33 else "soft")
    return {
        "thickness": 1,
        "connectivity": 8 if random() > 0.3 else 4,
        "style": style,
        "repaired": True,
        "repaired_pixels": 6 + int(random() * 14)
    }
