from agent.capability.capability_registry import (
    edit_existing_asset,
    generate_asset,
    inspect_asset,
    run_precon,
)
from agents.base_agent import BaseAgent


class ArtAgent(BaseAgent):
    """Visual asset production: Generation -> PReCon -> CreativeAsset.pixel."""

    name = "ArtAgent"
    capabilities = ("generation", "PReCon")

    def __init__(self):
        super().__init__()
        self.actions = {
            "create_character": self.create_character,
            "pixel_reconstruction": self.pixel_reconstruction,
            "edit_asset": self.edit_asset,
            "inspect_asset": self.inspect_asset,
        }

    def create_character(self, task, asset):
        return generate_asset(asset, task)

    def pixel_reconstruction(self, task, asset):
        return run_precon(asset, task)

    def edit_asset(self, task, asset):
        return edit_existing_asset(asset, task)

    def inspect_asset(self, task, asset):
        return inspect_asset(asset, task)
