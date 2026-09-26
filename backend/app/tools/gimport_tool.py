"""GImport Tool (Phase 15.4.11): route gimport to the engine exporter."""

from typing import Any

from app.core.config import settings
from app.engines.gimport.exporter.registry import register_default_exporters
from app.engines.gimport.pipeline.processor import GImportProcessor
from app.tools.base import BaseTool


class GImportTool(BaseTool):
    name = "gimport"

    def __init__(self, processor: GImportProcessor | None = None):
        register_default_exporters()
        self.processor = processor or GImportProcessor(
            default_target=settings.ENGINE_TARGET
        )

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        asset = context["asset"]
        plan = context.get("plan") or {}

        engine = dict(asset.get("engine") or {})
        engine["target"] = (
            plan.get("engine")
            or (context.get("request") or {}).get("engine")
            or engine.get("target")
            or settings.ENGINE_TARGET
        )
        asset["engine"] = engine

        asset = await self.processor.process(asset)
        context["asset"] = asset
        resources = asset["engine"]["resources"]
        return {
            "engine": resources["engine"],
            "files": sorted(resources["files"]),
            "quality": resources["quality"],
        }
