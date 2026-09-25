"""Agent Runtime: drives the Multi-Agent Supervisor in background threads
and streams its lifecycle events into the TaskStore for WebSocket fans."""

import threading

from agents.supervisor.supervisor import SupervisorAgent
from studio.backend.asset_service.service import AssetStore, TaskStore


class AgentRuntime:
    """POST /api/tasks -> runtime.start_task(goal) -> live event stream."""

    def __init__(self, supervisor=None):
        self.tasks = TaskStore()
        self.assets = AssetStore()
        self._supervisor = supervisor or SupervisorAgent()

    def start_task(self, goal):
        task_id = self.tasks.create(goal)
        thread = threading.Thread(
            target=self._run,
            args=(task_id, goal),
            name="creativeforge-task-{}".format(task_id),
            daemon=True
        )
        thread.start()
        return task_id

    def _run(self, task_id, goal):
        def on_event(event):
            self.tasks.append_event(task_id, event)
            if event["type"] == "TASK_COMPLETE" and event.get("asset_id"):
                pass  # asset saved below, once run() returns it

        try:
            result = self._supervisor.run(goal, on_event=on_event)
        except Exception as error:  # keep the task visible on failure
            self.tasks.fail(task_id, error)
            return

        self.tasks.finish(task_id, result)
        asset = result.get("asset")
        if asset:
            self.assets.save(asset)
            self.tasks.append_event(task_id, {
                "type": "ASSET_UPDATE",
                "id": asset.get("id"),
                "name": asset.get("name"),
                "engine": asset.get("engine", {}).get("target")
            })
