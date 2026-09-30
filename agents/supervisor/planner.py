from agent.planner.intent_analyzer import IntentAnalyzer


class SupervisorPlanner:
    """Builds a task graph from the current goal and optional asset context."""

    def __init__(self, intent_analyzer=None):
        self.intent_analyzer = intent_analyzer or IntentAnalyzer()

    def plan(self, goal, has_asset=False):
        intent = self.intent_analyzer.analyze(goal, has_asset=has_asset)
        requires = intent["requires"]
        tasks = []
        counter = [1]

        def add(agent, action, capability, **extra):
            task = {
                "id": "{:03d}".format(counter[0]),
                "agent": agent,
                "action": action,
                "capability": capability,
            }
            task.update(extra)
            tasks.append(task)
            counter[0] += 1

        if requires["generation"]:
            add("ArtAgent", "create_character", "generation")
        elif intent.get("modification"):
            add("ArtAgent", "edit_asset", "generation")

        if requires["pixel_reconstruction"]:
            add("ArtAgent", "pixel_reconstruction", "PReCon")
        if requires["animation_alignment"]:
            add("AnimationAgent", "create_animation", "FAlign")
        if requires["engine_import"]:
            add(
                "EngineAgent",
                "export_{}".format(intent["engine"]),
                "GImport",
                engine=intent["engine"],
            )

        if not tasks:
            add("ArtAgent", "inspect_asset", "generation")

        return {
            "goal": goal,
            "intent": intent,
            "tasks": tasks,
        }
