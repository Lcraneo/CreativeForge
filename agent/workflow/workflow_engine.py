from itertools import count

from agent.executor.task_executor import TaskExecutor
from agent.memory.task_memory import TaskMemory
from agent.recovery.recovery_manager import RecoveryManager


class WorkflowEngine:
    """Node/Edge/State execution over a plan, with checkpointing and
    failure recovery (LangGraph / Temporal style)."""

    def __init__(self, executor=None, memory=None, recovery=None):
        self.executor = executor or TaskExecutor()
        self.memory = memory or TaskMemory()
        self.recovery = recovery or RecoveryManager()
        self._workflow_ids = count(1)

    def run(self, plan, asset=None, resume=False):
        workflow_id = "{:03d}".format(next(self._workflow_ids))
        state = {
            "workflow_id": workflow_id,
            "goal": plan.get("goal"),
            "current": None,
            "state": "running",
            "steps": [],
        }

        if resume:
            latest = self.memory.latest_checkpoint()
            if latest is not None:
                asset = latest[1]

        completed = set(self.memory.checkpoints) if resume else set()

        for task in plan.get("tasks", []):
            if task["id"] in completed:
                state["steps"].append(
                    {"task": task["id"], "capability": task["capability"], "status": "skipped"}
                )
                continue

            state["current"] = task["capability"]
            task = dict(task, goal=plan.get("goal"))

            asset, recovery = self._run_task(task, asset)

            if asset is None:
                state["state"] = "failed"
                state["steps"].append(
                    {
                        "task": task["id"],
                        "capability": task["capability"],
                        "status": "failed",
                        "recovery": recovery,
                    }
                )
                return {"workflow": state, "asset": None}

            self.memory.save_checkpoint(task["id"], asset)
            state["steps"].append(
                {
                    "task": task["id"],
                    "capability": task["capability"],
                    "status": "success",
                    "recovery": recovery,
                }
            )

        state["state"] = "success"
        state["current"] = None
        return {"workflow": state, "asset": asset}

    def _run_task(self, task, asset):
        try:
            return self.executor.execute(task, asset), None
        except Exception as error:
            self.memory.record_error(task["id"], str(error))
            return self.recovery.recover(task, error, self.executor, asset)
