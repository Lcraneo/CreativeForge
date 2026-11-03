"""Engine adapters: same CreativeAsset, multiple target engines."""


class EngineAdapter:
    """Base interface for engine import/export (not bound to one engine)."""

    name = "engine"

    def import_asset(self, asset):
        raise NotImplementedError

    def export_project(self):
        raise NotImplementedError
