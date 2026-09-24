from agents.supervisor.planner import SupervisorPlanner
from agents.supervisor.task_router import TaskRouter
from agents.art_agent.art_agent import ArtAgent
from agents.animation_agent.animation_agent import AnimationAgent
from agents.engine_agent.engine_agent import EngineAgent
from agents.qa_agent.qa_agent import QAAgent
from agents.memory_agent.memory_agent import MemoryAgent
from agent.recovery.recovery_manager import RecoveryManager
from protocol.message import AgentMessage, MessageBus

REPAIR_ACTIONS = {
    "pixel": ("ArtAgent", "pixel_reconstruction", "PReCon"),
    "animation": ("AnimationAgent", "create_animation", "FAlign"),
    "engine": ("EngineAgent", "export_engine", "GImport")
}


class AgentExecutorAdapter:
    """Lets the Phase 6 RecoveryManager route tasks through agents."""

    def __init__(self, router):
        self.router = router

    def execute(self, task, asset):
        return self.router.dispatch(task, asset)


class SupervisorAgent:
    """The brain of the Multi-Agent System.

    Goal -> Planner -> dispatch task graph to agents (Art / Animation /
    Engine) -> QA Agent -> repair round if needed -> Memory Agent -> output.
    """

    name = "SupervisorAgent"
    MAX_REPAIR_ROUNDS = 1

    def __init__(self):
        self.planner = SupervisorPlanner()
        self.bus = MessageBus()
        self.router = TaskRouter()
        for agent in (ArtAgent(), AnimationAgent(), EngineAgent(), QAAgent(), MemoryAgent()):
            self.router.register(agent)
            self.bus.register(agent.name)
        self.bus.register(self.name)
        self.recovery = RecoveryManager(max_retries=1)
        self.executor = AgentExecutorAdapter(self.router)

    def run(self, goal, asset=None):
        plan = self.planner.plan(goal)
        steps = []
        messages = []

        previous_agent = None
        for task in plan["tasks"]:
            task = dict(task, goal=plan["goal"])
            asset = self._execute_task(task, asset, steps, messages)
            if asset is None:
                return {
                    "goal": goal,
                    "plan": plan,
                    "supervisor": {
                        "status": "failed",
                        "steps": steps
                    },
                    "asset": None,
                    "messages": messages
                }

            if previous_agent is not None and previous_agent != task["agent"]:
                self._send(
                    previous_agent,
                    task["agent"],
                    "ASSET_READY",
                    {"asset_id": asset.get("id"), "from": previous_agent},
                    messages
                )
            previous_agent = task["agent"]

        qa_task = {
            "id": "QA1",
            "agent": "QAAgent",
            "action": "quality_check",
            "capability": "QA",
            "goal": plan["goal"]
        }
        asset = self._execute_task(qa_task, asset, steps, messages)
        if asset is None:
            return {
                "goal": goal,
                "plan": plan,
                "supervisor": {"status": "failed", "steps": steps},
                "asset": None,
                "messages": messages
            }

        report = asset.get("quality", {}).get("report", {})
        repair_rounds = 0
        while report.get("status") == "RETRY" and repair_rounds < self.MAX_REPAIR_ROUNDS:
            repair_rounds += 1
            for repair_task in self._repair_tasks(report, plan):
                asset = self._execute_task(repair_task, asset, steps, messages)
                if asset is None:
                    return {
                        "goal": goal,
                        "plan": plan,
                        "supervisor": {"status": "failed", "steps": steps},
                        "asset": None,
                        "messages": messages
                    }
            asset = self._execute_task(qa_task, asset, steps, messages)
            report = asset.get("quality", {}).get("report", {})

        self._send(
            "QAAgent",
            self.name,
            "QUALITY_REPORT",
            {"status": report.get("status"), "score": report.get("scores")},
            messages
        )

        memory_task = {
            "id": "M01",
            "agent": "MemoryAgent",
            "action": "save_checkpoint",
            "capability": "Memory",
            "goal": plan["goal"]
        }
        asset = self._execute_task(memory_task, asset, steps, messages)

        status = report.get("status", "success")
        return {
            "goal": goal,
            "plan": plan,
            "supervisor": {
                "status": status,
                "qa_rounds": repair_rounds,
                "steps": steps
            },
            "asset": asset,
            "messages": messages,
            "memory": asset.get("memory", {}) if asset else {}
        }

    def _execute_task(self, task, asset, steps, messages):
        try:
            result = self.router.dispatch(task, asset)
        except Exception as error:
            result, recovery = self.recovery.recover(
                task, error, self.executor, asset
            )
            if result is None:
                self._send(
                    task.get("agent", "system"),
                    self.name,
                    "RECOVERY_REQUEST",
                    {"task": task.get("id"), "reason": recovery.get("reason")},
                    messages
                )
                steps.append({
                    "task": task.get("id"),
                    "agent": task.get("agent"),
                    "action": task.get("action"),
                    "status": "failed",
                    "recovery": recovery
                })
                return None
            steps.append({
                "task": task.get("id"),
                "agent": task.get("agent"),
                "action": task.get("action"),
                "status": "recovered",
                "recovery": recovery
            })
            return result

        steps.append({
            "task": task.get("id"),
            "agent": task.get("agent"),
            "action": task.get("action"),
            "status": "success"
        })
        return result

    def _repair_tasks(self, report, plan):
        engine = plan["intent"]["engine"]
        tasks = []
        for index, section in enumerate(report.get("retry", []), start=1):
            agent, action, capability = REPAIR_ACTIONS[section]
            task = {
                "id": "R{:02d}".format(index),
                "agent": agent,
                "action": action,
                "capability": capability,
                "repair": True
            }
            if capability == "GImport":
                task["engine"] = engine
            tasks.append(task)
        return tasks

    def _send(self, sender, receiver, type, payload, messages):
        message = AgentMessage(sender, receiver, type, payload)
        self.bus.send(message)
        messages.append(message.to_dict())
