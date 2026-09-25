"""In-memory task + asset stores (the Studio's data center)."""

import threading
import time


class TaskStore:
    """task_id -> {goal, status, plan, steps, events, asset summary}."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}
        self._counter = 0

    def create(self, goal):
        with self._lock:
            self._counter += 1
            task_id = "T{:04d}".format(self._counter)
            self._tasks[task_id] = {
                "task_id": task_id,
                "goal": goal,
                "status": "running",
                "created_at": time.time(),
                "plan": None,
                "events": [],
                "asset_id": None,
                "error": None
            }
            return task_id

    def append_event(self, task_id, event):
        event = dict(event, at=time.time())
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["events"].append(event)
                if event["type"] == "PLAN_CREATED":
                    task["plan"] = event.get("plan")
        return event

    def finish(self, task_id, result):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = result["supervisor"]["status"].lower()
            asset = result.get("asset")
            task["asset_id"] = asset.get("id") if asset else None
            task["result"] = result

    def fail(self, task_id, error):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["status"] = "failed"
                task["error"] = str(error)

    def get(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def list(self, limit=20):
        with self._lock:
            tasks = sorted(self._tasks.values(),
                           key=lambda item: item["created_at"],
                           reverse=True)
            return [self._summary(task) for task in tasks[:limit]]

    @staticmethod
    def _summary(task):
        return {
            "task_id": task["task_id"],
            "goal": task["goal"],
            "status": task["status"],
            "created_at": task["created_at"],
            "asset_id": task["asset_id"],
            "event_count": len(task["events"])
        }


class AssetStore:
    """CreativeAssets produced by the runtime, indexed by asset id."""

    def __init__(self):
        self._lock = threading.Lock()
        self._assets = {}
        self._order = []

    def save(self, asset):
        with self._lock:
            asset_id = asset.get("id")
            if asset_id not in self._assets:
                self._order.append(asset_id)
            self._assets[asset_id] = asset
            return asset_id

    def get(self, asset_id):
        with self._lock:
            return self._assets.get(asset_id)

    def latest(self):
        with self._lock:
            if not self._order:
                return None
            return self._assets[self._order[-1]]

    def list(self):
        with self._lock:
            return [
                {"id": asset_id, "name": self._assets[asset_id].get("name"),
                 "type": self._assets[asset_id].get("type")}
                for asset_id in reversed(self._order)
            ]
