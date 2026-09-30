from agent.capability.capability_registry import run_gimport
from agents.base_agent import BaseAgent


class EngineAgent(BaseAgent):
    """Game engine production: GImport -> engine-ready resources."""

    name = "EngineAgent"
    capabilities = ("GImport",)
    engines = ("unity", "cocos", "godot")

    def __init__(self):
        super().__init__()
        self.actions = {"export_engine": self.export_engine}
        for engine in self.engines:
            self.actions["export_{}".format(engine)] = self._make_export(engine)

    def _make_export(self, engine):
        def export(task, asset):
            return run_gimport(asset, dict(task, engine=engine))

        return export

    def export_engine(self, task, asset):
        return run_gimport(asset, task)
