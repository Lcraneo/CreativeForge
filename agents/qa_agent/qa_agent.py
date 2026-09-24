from agents.base_agent import BaseAgent
from agent.monitor.quality_gate import QualityGate

SECTION_CHECKS = {
    "pixel": "palette / outline / style",
    "animation": "drift / jitter / phase",
    "engine": "missing asset / runtime error"
}


class QAAgent(BaseAgent):
    """Generate -> Validate -> Repair loop: unified quality verdict over the
    sections written by PReCon / FAlign / GImport."""

    name = "QAAgent"
    capabilities = ("QA",)

    def __init__(self):
        super().__init__()
        self.actions = {
            "quality_check": self.quality_check
        }
        self.quality_gate = QualityGate()

    def quality_check(self, task, asset):
        verdict = self.quality_gate.check(asset)
        report = dict(verdict)
        report["sections"] = dict(SECTION_CHECKS)
        asset.setdefault("quality", {})["report"] = report
        return asset
