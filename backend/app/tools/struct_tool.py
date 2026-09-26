"""Struct Tool (Phase 13.12): route structure_asset to the engine."""

from typing import Any

from app.engines.asset_struct.processor import AssetStructProcessor
from app.tools.base import BaseTool


class StructTool(BaseTool):
    name = "structure_asset"

    def __init__(self, processor: AssetStructProcessor | None = None):
        self.processor = processor or AssetStructProcessor()

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        asset = await self.processor.process(context["asset"])
        context["asset"] = asset
        return {
            "layers": [layer["name"] for layer in asset["content"]["layers"]],
            "segmentation_score": asset["quality"]["segmentation_score"],
        }
