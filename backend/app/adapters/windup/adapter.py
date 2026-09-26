"""WindupAdapter (Phase 12.7)."""

from typing import Any

from app.adapters.base import AssetAdapter
from app.adapters.windup.client import MockWindupClient, WindupClient
from app.adapters.windup.mapper import map_to_asset


class WindupAdapter(AssetAdapter):
    name = "windup"

    def __init__(self, client: WindupClient | MockWindupClient, style: str = "anime"):
        self.client = client
        self.style = style

    async def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.generate(
            request["prompt"], style=request.get("style") or self.style
        )
        return await self.convert(result)

    async def convert(self, raw_asset: dict[str, Any]) -> dict[str, Any]:
        return map_to_asset(raw_asset)
