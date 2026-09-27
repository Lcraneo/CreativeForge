from ..grid import infer_grid
from ..palette import reconstruct_palette
from ..contour import repair_contour
from ..quality import evaluate_pixel


class PReConEngine:

    def process(self, image, style=None):
        """Reconstruct a pixel/2D asset from the generation source.

        ``style`` ("pixel" / "2d") steers palette width and contour treatment;
        the seedless pixel path keeps the frozen benchmark baseline.
        """

        grid = infer_grid(image)

        palette = reconstruct_palette(
            image,
            style
        )

        contour = repair_contour(
            image,
            style
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
                "contour": contour,
                "style": style or "pixel"
            },
            "quality": quality
        }
