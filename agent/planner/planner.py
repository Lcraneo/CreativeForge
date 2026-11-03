from agent.planner.intent_analyzer import IntentAnalyzer


class Planner:
    """Turns a user goal into an executable task plan.

    The plan references capabilities (generation / PReCon / FAlign / GImport),
    never concrete code.
    """

    def __init__(self, intent_analyzer=None):
        self.intent_analyzer = intent_analyzer or IntentAnalyzer()

    def plan(self, goal):
        intent = self.intent_analyzer.analyze(goal)
        requires = intent["requires"]

        tasks = [{"id": "task1", "name": "generate_asset", "capability": "generation"}]

        next_index = 2

        if requires["pixel_reconstruction"]:
            tasks.append(
                {
                    "id": "task{}".format(next_index),
                    "name": "pixel_reconstruction",
                    "capability": "PReCon",
                }
            )
            next_index += 1

        if requires["animation_alignment"]:
            tasks.append(
                {
                    "id": "task{}".format(next_index),
                    "name": "animation_alignment",
                    "capability": "FAlign",
                }
            )
            next_index += 1

        if requires["engine_import"]:
            tasks.append(
                {
                    "id": "task{}".format(next_index),
                    "name": "engine_import",
                    "capability": "GImport",
                    "engine": intent["engine"],
                }
            )

        return {"goal": goal, "intent": intent, "tasks": tasks}
