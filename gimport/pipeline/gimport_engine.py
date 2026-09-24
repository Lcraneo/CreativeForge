from gimport.manifest.manifest_generator import ManifestGenerator
from gimport.atlas.sprite_atlas_builder import SpriteAtlasBuilder
from gimport.animation.animation_clip_generator import AnimationClipGenerator
from gimport.prefab.prefab_generator import PrefabGenerator
from gimport.adapters.registry import ENGINE_ADAPTERS
from gimport.validation.runtime_validator import RuntimeValidator


class GImportEngine:
    """Manifest -> Atlas -> Animation Clip -> Prefab -> Engine Adapter -> Validation."""

    def __init__(self):
        self.manifest = ManifestGenerator()
        self.atlas = SpriteAtlasBuilder()
        self.animation = AnimationClipGenerator()
        self.prefab = PrefabGenerator()
        self.adapters = dict(ENGINE_ADAPTERS)
        self.validator = RuntimeValidator()

    def process(self, asset, engine="cocos"):
        adapter = self.adapters.get(engine, self.adapters["cocos"])()

        manifest = self.manifest.generate(asset)

        atlas = self.atlas.build(asset)

        animation = self.animation.generate(asset, engine)

        prefab = self.prefab.generate(asset)

        engine_export = adapter.import_asset(asset)

        result = {
            "manifest": manifest,
            "atlas": atlas,
            "animation": animation,
            "prefab": prefab,
            "engine": engine_export
        }

        validation = self.validator.check(result)

        result["validation"] = validation

        return result
