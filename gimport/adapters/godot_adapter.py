from gimport.adapters import EngineAdapter


class GodotAdapter(EngineAdapter):

    name = "godot"
    layout = ["textures", "animations", "scenes"]

    def import_asset(self, asset):
        asset_id = asset.get("id", "asset000")
        return {
            "engine": self.name,
            "layout": list(self.layout),
            "resources": {
                "textures": "textures/{}.png".format(asset_id),
                "animations": "animations/{}.tres".format(asset_id),
                "scenes": "scenes/{}.tscn".format(asset_id)
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
