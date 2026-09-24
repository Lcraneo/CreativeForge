from agent.capability.capability_registry import build_default_registry
from agent.executor.task_executor import TaskExecutor
from agent.memory.task_memory import TaskMemory
from agent.monitor.quality_gate import QualityGate
from agent.planner.planner import Planner
from agent.workflow.workflow_engine import WorkflowEngine


class CreativeAgent:
    """Phase 6 entry point.

    User goal -> Intent Analyzer -> Planner -> Workflow Executor
    (generation / PReCon / FAlign / GImport) -> Quality Gate -> output.
    """

    def __init__(self, registry=None):
        self.memory = TaskMemory()
        self.planner = Planner()
        self.quality_gate = QualityGate()
        self.workflow = WorkflowEngine(
            executor=TaskExecutor(registry or build_default_registry()),
            memory=self.memory
        )

    def run(self, goal, asset=None):
        plan = self.planner.plan(goal)

        self.memory.save_goal(goal)
        self.memory.save_plan(plan)

        result = self.workflow.run(plan, asset)

        quality = self.quality_gate.check(result["asset"] or {})

        return {
            "goal": goal,
            "plan": plan,
            "workflow": result["workflow"],
            "asset": result["asset"],
            "quality": quality,
            "memory": self.memory.summary()
        }
