import copy


class TaskMemory:
    """Long-task memory: goal, plan, completed steps, asset versions, errors
    and checkpoints (CreativeAsset as evolving state)."""

    def __init__(self):
        self.goal = None
        self.plan = None
        self.completed_steps = []
        self.asset_versions = []
        self.errors = []
        self.checkpoints = {}

    def save_goal(self, goal):
        self.goal = goal

    def save_plan(self, plan):
        self.plan = copy.deepcopy(plan)

    def save_checkpoint(self, task_id, asset):
        self.checkpoints[task_id] = copy.deepcopy(asset)
        self.completed_steps.append(task_id)
        self.asset_versions.append({
            "task": task_id,
            "asset": copy.deepcopy(asset)
        })

    def record_error(self, task_id, message):
        self.errors.append({"task": task_id, "message": message})

    def latest_checkpoint(self):
        if not self.checkpoints:
            return None
        task_id = self.completed_steps[-1]
        return task_id, copy.deepcopy(self.checkpoints[task_id])

    def summary(self):
        return {
            "goal": self.goal,
            "completed_steps": list(self.completed_steps),
            "errors": list(self.errors),
            "checkpoints": list(self.checkpoints)
        }
