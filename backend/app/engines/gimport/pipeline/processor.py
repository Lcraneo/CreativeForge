"""GImport processor (Phase 15.4.10): the unified engine-import entry.

    CreativeAsset -> GImportProcessor -> Engine Asset

The engine target comes from `asset["engine"]["target"]` (or the caller's
default) and the export result is written back onto
`asset["engine"]["resources"]` with a quality block.
"""

from typing import Any

from app.engines.gimport.exporter.registry import registry as exporter_registry


class GImportProcessor:
    name = "gimport"

    def __init__(self, registry=exporter_registry, default_target: str = "cocos"):
        self.registry = registry
        self.default_target = default_target

    async def process(self, asset: dict[str, Any]) -> dict[str, Any]:
        target = (asset.get("engine") or {}).get("target") or self.default_target
        exporter = self.registry.get(target)
        if exporter is None:
            raise ValueError(f"unknown engine target: {target}")

        result = await exporter.export(asset)

        engine = dict(asset.get("engine") or {})
        engine["target"] = target
        engine["resources"] = result
        asset["engine"] = engine

        quality = dict(asset.get("quality") or {})
        quality["import"] = (result.get("quality") or {}).get("manifest_score", 0.0)
        asset["quality"] = quality
        return asset
