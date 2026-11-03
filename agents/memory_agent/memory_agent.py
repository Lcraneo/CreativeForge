from agent.memory.task_memory import TaskMemory
from agents.base_agent import BaseAgent


class MemoryAgent(BaseAgent):
    """Long-task memory: user style, asset versions, task history, error
    records and checkpoints (keeps style consistent across tasks)."""

    name = "MemoryAgent"
    capabilities = ("Memory",)

    def __init__(self):
        super().__init__()
        self.actions = {
            "save_checkpoint": self.save_checkpoint,
            "remember_style": self.remember_style,
        }
        self.memory = TaskMemory()
        self.user_style = None

    def save_checkpoint(self, task, asset):
        self.memory.save_goal(task.get("goal"))
        self.memory.save_checkpoint(task.get("id", "supervisor"), asset)
        self.remember_style(task, asset)
        asset.setdefault("memory", {})["checkpoint"] = self.memory.summary()
        return asset

    def remember_style(self, task, asset):
        self.user_style = {
            "style": "pixel",
            "palette": (asset.get("pixel", {}).get("palette", {}).get("max_colors", 16)),
            "engine": asset.get("engine", {}).get("target"),
        }
        asset.setdefault("memory", {})["user_style"] = self.user_style
        return asset
