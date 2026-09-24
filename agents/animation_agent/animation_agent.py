from agents.base_agent import BaseAgent
from agent.capability.capability_registry import run_falign


class AnimationAgent(BaseAgent):
    """Animation production: Animation Source -> FAlign -> Animation Asset."""

    name = "AnimationAgent"
    capabilities = ("FAlign",)

    def __init__(self):
        super().__init__()
        self.actions = {
            "create_animation": self.create_animation
        }

    def create_animation(self, task, asset):
        return run_falign(asset, task)
