from agent.planner.intent_analyzer import IntentAnalyzer


class SupervisorPlanner:
    """Goal -> task graph with agent assignments (Supervisor brain)."""

    def __init__(self, intent_analyzer=None):
        self.intent_analyzer = intent_analyzer or IntentAnalyzer()

    def plan(self, goal):
        intent = self.intent_analyzer.analyze(goal)
        requires = intent["requires"]

        tasks = []
        counter = [1]

        def add(agent, action, capability, **extra):
            task = {
                "id": "{:03d}".format(counter[0]),
                "agent": agent,
                "action": action,
                "capability": capability
            }
            task.update(extra)
            tasks.append(task)
            counter[0] += 1

        add("ArtAgent", "create_character", "generation")
        if requires["pixel_reconstruction"]:
            add("ArtAgent", "pixel_reconstruction", "PReCon")
        if requires["animation_alignment"]:
            add("AnimationAgent", "create_animation", "FAlign")
        if requires["engine_import"]:
            add(
                "EngineAgent",
                "export_{}".format(intent["engine"]),
                "GImport",
                engine=intent["engine"]
            )

        return {
            "goal": goal,
            "intent": intent,
            "tasks": tasks
        }
