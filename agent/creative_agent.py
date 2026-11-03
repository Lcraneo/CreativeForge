import time

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
            executor=TaskExecutor(registry or build_default_registry()), memory=self.memory
        )

    def run(self, goal, asset=None):
        plan = self.planner.plan(goal)

        self.memory.save_goal(goal)
        self.memory.save_plan(plan)

        # perf_counter 计时开销可忽略；内存峰值留给发布门（tracemalloc 会拖慢 2-4x）
        started = time.perf_counter()
        result = self.workflow.run(plan, asset)
        execution_ms = (time.perf_counter() - started) * 1000

        if isinstance(result.get("asset"), dict):
            asset_out = result["asset"]
            meta = dict(asset_out.get("meta") or {})
            meta["performance"] = {"execution_ms": round(execution_ms, 1)}
            asset_out["meta"] = meta

        quality = self.quality_gate.check(result["asset"] or {})

        return {
            "goal": goal,
            "plan": plan,
            "workflow": result["workflow"],
            "asset": result["asset"],
            "quality": quality,
            "memory": self.memory.summary(),
        }
