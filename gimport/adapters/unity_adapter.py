from gimport.adapters import EngineAdapter


class UnityAdapter(EngineAdapter):

    name = "unity"
    layout = ["Texture", "Animation", "Prefab", "Controller"]

    def import_asset(self, asset):
        asset_id = asset.get("id", "asset000")
        return {
            "engine": self.name,
            "layout": list(self.layout),
            "resources": {
                "Texture": "Assets/Texture/{}.png".format(asset_id),
                "Animation": "Assets/Animation/{}.anim".format(asset_id),
                "Prefab": "Assets/Prefab/{}.prefab".format(asset_id),
                "Controller": "Assets/Controller/{}.controller".format(asset_id)
            }
        }

    def export_project(self):
        return {
            "engine": self.name,
            "project": {
                directory: []
                for directory in self.layout
            }
        }
