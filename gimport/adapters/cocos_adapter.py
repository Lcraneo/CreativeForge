from gimport.adapters import EngineAdapter


class CocosAdapter(EngineAdapter):

    name = "cocos"
    layout = ["textures", "atlas", "animations", "prefabs"]

    def import_asset(self, asset):
        asset_id = asset.get("id", "asset000")
        return {
            "engine": self.name,
            "layout": list(self.layout),
            "resources": {
                "textures": "assets/textures/{}.png".format(asset_id),
                "atlas": "assets/atlas/{}_sprite_atlas.plist".format(asset_id),
                "animations": "assets/animations/{}.anim".format(asset_id),
                "prefabs": "assets/prefabs/{}.prefab".format(asset_id)
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
