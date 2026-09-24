from core.adapter import AssetAdapter
from falign.pipeline.falign_engine import FAlignEngine


class CreativeAssetAdapter(AssetAdapter):
    """FAlign <-> CreativeAsset integration (Phase 4, section 10).

    Runs the FAlign pipeline over ``CreativeAsset.animation.frames`` and
    writes the aligned animation state (frames / anchor / phase / motion)
    plus ``quality.animation`` back into the asset.
    """

    def __init__(self):
        self.engine = FAlignEngine()

    def name(self) -> str:
        return "falign"

    def version(self) -> str:
        return "1.0"

    def can_handle(self, asset_type: str) -> bool:
        return asset_type == "animation"

    def import_asset(self, source):
        return source

    def export_asset(self, asset):
        frames = asset.get("animation", {}).get("frames", [])
        result = self.engine.process(frames)

        animation = dict(asset.get("animation", {}))
        animation.update(result["animation"])
        asset["animation"] = animation

        quality = dict(asset.get("quality", {}))
        quality.update(result["quality"])
        asset["quality"] = quality
        return asset
