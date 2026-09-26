"""Adapter interface (Phase 12.4).

External AI never touches the pipeline directly:

    Windup -> WindupAdapter -> CreativeAsset

Adapters own `generate` (call the provider) and `convert` (map the raw
payload onto the CreativeAsset contract).
"""

from abc import ABC, abstractmethod
from typing import Any


class AssetAdapter(ABC):
    name: str

    @abstractmethod
    async def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Call the external provider and return a CreativeAsset dict."""
        raise NotImplementedError

    @abstractmethod
    async def convert(self, raw_asset: dict[str, Any]) -> dict[str, Any]:
        """Map a raw provider payload onto the CreativeAsset contract."""
        raise NotImplementedError
