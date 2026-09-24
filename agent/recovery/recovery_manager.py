class RecoveryManager:
    """Retry -> Fallback -> Human-in-loop."""

    def __init__(self, max_retries=2):
        self.max_retries = max_retries

    def recover(self, task, error, executor, asset):
        last_error = error

        for attempt in range(1, self.max_retries + 1):
            try:
                return (
                    executor.execute(task, asset),
                    {"strategy": "retry", "attempts": attempt}
                )
            except Exception as retry_error:
                last_error = retry_error

        fallback_task = self._fallback(task)
        if fallback_task is not None:
            try:
                return (
                    executor.execute(fallback_task, asset),
                    {"strategy": "fallback", "task": fallback_task}
                )
            except Exception as fallback_error:
                last_error = fallback_error

        return (
            None,
            {
                "strategy": "human-in-loop",
                "reason": str(last_error)
            }
        )

    def _fallback(self, task):
        if task.get("capability") == "GImport" and task.get("engine") == "unity":
            return dict(task, engine="cocos")
        return None
