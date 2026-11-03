PREFAB_COMPONENTS = [
    "SpriteRenderer",
    "Animator",
    "Collider",
    "Script",
    "AnimationController"
]


class PrefabGenerator:
    """Generates the ready-to-use character entity (prefab)."""

    def generate(self, asset):
        asset_id = asset.get("id", "asset000")
        return {
            "prefab": {
                "name": "{}.prefab".format(asset_id),
                "root": asset_id,
                "components": list(PREFAB_COMPONENTS)
            }
        }
