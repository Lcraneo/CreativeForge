from agents.base_agent import BaseAgent
from agent.capability.capability_registry import generate_asset, run_precon


class ArtAgent(BaseAgent):
    """Visual asset production: Generation -> PReCon -> CreativeAsset.pixel."""

    name = "ArtAgent"
    capabilities = ("generation", "PReCon")

    def __init__(self):
        super().__init__()
        self.actions = {
            "create_character": self.create_character,
            "pixel_reconstruction": self.pixel_reconstruction
        }

    def create_character(self, task, asset):
        return generate_asset(asset, task)

    def pixel_reconstruction(self, task, asset):
        return run_precon(asset, task)
