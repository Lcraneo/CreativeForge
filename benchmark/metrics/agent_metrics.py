"""Agent benchmark metrics (Phase 9, section 九).

Validates the autonomous planning layer (Phase 6/7): the agent is not a
simple API wrapper — it plans, dispatches, recovers and completes complex
asset production goals on its own.

Metrics:
    Task Completion Rate    goals that end with supervisor status PASS
    Planning Accuracy       planned capability graph matches the goal intent
    Recovery Success Rate   failures repaired by retry / fallback
    Average Task Time       wall-clock seconds per completed goal
"""

import time

# Expected capability graph per goal shape, used to score planning accuracy.
EXPECTED_CAPABILITIES = {
    "animated": ["generation", "PReCon", "FAlign", "GImport"],
    "static": ["generation", "PReCon", "GImport"]
}


def planning_accuracy(plan, entry):
    """1.0 when the planned capability sequence matches the goal intent."""
    expected = EXPECTED_CAPABILITIES[
        "animated" if entry["frames"] > 0 else "static"
    ]
    planned = [task["capability"] for task in plan["tasks"]]
    engine_ok = plan["intent"]["engine"] == entry["engine"]
    return 1.0 if planned == expected and engine_ok else 0.0


def recovery_success_rate(rounds=3):
    """Force an engine failure and measure the fallback repair success.

    Mirrors the production scenario: the requested engine (unity) fails,
    the RecoveryManager must recover via fallback (unity -> cocos).
    """
    from agent.recovery.recovery_manager import RecoveryManager

    class FailingUnityExecutor:
        def __init__(self):
            self.calls = []

        def execute(self, task, asset):
            self.calls.append(task.get("engine"))
            if task.get("engine") == "unity":
                raise ValueError("engine failure")
            return asset

    successes = 0
    executor = FailingUnityExecutor()
    manager = RecoveryManager(max_retries=1)
    for _ in range(rounds):
        asset, recovery = manager.recover(
            {"id": "T1", "capability": "GImport", "engine": "unity"},
            ValueError("first failure"),
            executor,
            {"id": "hero001"}
        )
        if asset is not None and recovery.get("strategy") == "fallback":
            successes += 1
    return round(successes / float(rounds), 4)


def evaluate(entries):
    """Run the real Multi-Agent Supervisor over every dataset entry."""
    from agents.supervisor.supervisor import SupervisorAgent

    supervisor = SupervisorAgent()
    completed = 0
    accuracy = 0.0
    total_time = 0.0
    details = []

    for entry in entries:
        start = time.perf_counter()
        result = supervisor.run(entry["goal"])
        elapsed = time.perf_counter() - start
        total_time += elapsed

        status = result["supervisor"]["status"]
        success = status == "PASS" and result["asset"] is not None
        completed += 1 if success else 0
        accuracy += planning_accuracy(result["plan"], entry)
        details.append({
            "id": entry["id"],
            "goal": entry["goal"],
            "status": status,
            "steps": len(result["supervisor"]["steps"]),
            "seconds": round(elapsed, 4)
        })

    total = len(entries)
    return {
        "task_completion_rate": round(completed / float(total), 4) if total else 0.0,
        "planning_accuracy": round(accuracy / float(total), 4) if total else 0.0,
        "recovery_success_rate": recovery_success_rate(),
        "average_task_seconds": round(total_time / total, 4) if total else 0.0,
        "completed": completed,
        "total": total,
        "details": details
    }
