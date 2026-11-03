from gimport.pipeline.gimport_engine import GImportEngine

EXPORT_CONTENTS = ["Character", "Animation", "Prefab", "Config"]


class OneClickExporter:
    """End-user experience: one click from CreativeAsset to a shareable
    engine-ready game asset package."""

    def __init__(self, engine=None):
        self.engine = engine or GImportEngine()

    def export(self, asset, engine="cocos"):
        import time

        result = self.engine.process(asset, engine)
        name = asset.get("name", asset.get("id", "Asset"))
        return {
            # 包名带引擎+毫秒时间戳：此前同一资产三引擎导出共用
            # "{name}GameAsset.zip"，后写覆盖先写——先前返回的 download_url
            # 会下载到别的引擎的内容
            "package": "{}_{}_{}_GameAsset.zip".format(
                name, engine, int(time.time() * 1000)
            ),
            "engine": engine,
            "contents": list(EXPORT_CONTENTS),
            "result": result
        }
