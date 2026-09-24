from gimport.manifest.schema import validate_manifest


class ManifestGenerator:
    """Generates the asset manifest: the asset's ID card for the engine."""

    def generate(self, asset):
        asset_id = asset.get("id", "asset000")
        manifest = {
            "asset_id": asset_id,
            "type": asset.get("type", "character"),
            "resources": {
                "texture": "{}.png".format(asset_id),
                "animation": "{}.anim".format(asset_id),
                "prefab": "{}.prefab".format(asset_id)
            }
        }
        manifest["valid"] = validate_manifest(manifest)["valid"]
        return manifest
