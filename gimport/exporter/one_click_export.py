from gimport.pipeline.gimport_engine import GImportEngine

EXPORT_CONTENTS = ["Character", "Animation", "Prefab", "Config"]


class OneClickExporter:
    """End-user experience: one click from CreativeAsset to a shareable
    engine-ready game asset package."""

    def __init__(self, engine=None):
        self.engine = engine or GImportEngine()

    def export(self, asset, engine="cocos"):
        result = self.engine.process(asset, engine)
        name = asset.get("name", asset.get("id", "Asset"))
        return {
            "package": "{}GameAsset.zip".format(name),
            "engine": engine,
            "contents": list(EXPORT_CONTENTS),
            "result": result
        }
