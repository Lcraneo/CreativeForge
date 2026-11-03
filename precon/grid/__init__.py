from precon._seed import clamp, rng, seed_of


def infer_grid(image):
    """Grid inference: fixed 8×8 contract, prompt-specific phase + confidence."""

    size = int(image.get("grid_size", 8) or 8)
    seed = seed_of(image)

    if seed is None:
        return {
            "size": size,
            "phase_x": 0,
            "phase_y": 0,
            "confidence": 0.9
        }

    random = rng(seed, salt=1)
    return {
        "size": size,
        "phase_x": round(random() * 0.5, 3),
        "phase_y": round(random() * 0.5, 3),
        "confidence": round(clamp(0.86 + 0.12 * random(), 0.8, 0.99), 3)
    }
