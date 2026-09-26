"""Exporter registry (Phase 15.4.8): pick the engine adapter by target."""

from typing import Optional

from app.engines.gimport.exporter.base import EngineExporter


class ExporterRegistry:
    def __init__(self):
        self.exporters: dict[str, EngineExporter] = {}

    def register(self, exporter: EngineExporter) -> None:
        self.exporters[exporter.name] = exporter

    def get(self, name: str) -> Optional[EngineExporter]:
        return self.exporters.get(name)

    def names(self) -> list[str]:
        return sorted(self.exporters)


registry = ExporterRegistry()


def register_default_exporters() -> ExporterRegistry:
    """Idempotent bootstrap of the built-in engine exporters."""
    from app.engines.gimport.exporter.cocos import CocosExporter
    from app.engines.gimport.exporter.godot import GodotExporter
    from app.engines.gimport.exporter.unity import UnityExporter

    for exporter in (CocosExporter(), UnityExporter(), GodotExporter()):
        registry.register(exporter)
    return registry


def engine_names() -> list[str]:
    """Registered engine targets (register_default_exporters first)."""
    register_default_exporters()
    return registry.names()
