from .grid import infer_grid
from .palette import reconstruct_palette
from .contour import repair_contour
from .quality import evaluate_pixel


class PReConEngine:

    def process(self, image, style=None):

        grid = infer_grid(image)

        palette = reconstruct_palette(
            image,
            style
        )

        contour = repair_contour(
            image
        )

        quality = evaluate_pixel(
            grid,
            palette,
            contour
        )

        return {
            "pixel": {
                "grid": grid,
                "palette": palette,
                "contour": contour
            },
            "quality": quality
        }
