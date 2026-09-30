def map_image(image):

    return {
        "visual": {
            "width": image.get("width"),
            "height": image.get("height"),
            "has_alpha": image.get("alpha", False),
        }
    }
