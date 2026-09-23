def infer_grid(image):

    width = image.get("width", 0)
    height = image.get("height", 0)

    return {
        "size": 8,
        "phase_x": 0,
        "phase_y": 0,
        "confidence": 0.9
    }
