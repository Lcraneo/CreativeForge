"""Adapter registry (Phase 12.8) + startup bootstrap.

`setup_adapters` picks the real Windup client when credentials are
configured and the deterministic mock otherwise.
"""

from typing import Optional

from app.adapters.base import AssetAdapter


class AdapterRegistry:
    def __init__(self):
        self.adapters: dict[str, AssetAdapter] = {}

    def register(self, adapter: AssetAdapter) -> None:
        self.adapters[adapter.name] = adapter

    def get(self, name: str) -> Optional[AssetAdapter]:
        return self.adapters.get(name)

    def names(self) -> list[str]:
        return sorted(self.adapters)


registry = AdapterRegistry()


def setup_adapters() -> AdapterRegistry:
    from app.adapters.holonic.adapter import HolonicAdapter
    from app.adapters.windup.adapter import WindupAdapter
    from app.adapters.windup.client import MockWindupClient, WindupClient
    from app.core.config import settings

    if settings.use_mock_generation:
        client = MockWindupClient()
    else:
        client = WindupClient(settings.WINDUP_API_KEY, settings.WINDUP_BASE_URL)

    registry.register(WindupAdapter(client, style=settings.WINDUP_STYLE))
    if "holonic" not in registry.adapters:
        registry.register(HolonicAdapter())
    return registry


def ensure_adapters() -> AdapterRegistry:
    """Lazy idempotent bootstrap so tools work without app lifespan."""
    if "windup" not in registry.adapters:
        setup_adapters()
    return registry
