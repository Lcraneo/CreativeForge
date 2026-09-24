from protocol.state import AgentState


class BaseAgent:
    """Specialist agent base: named, stateful, handles a fixed action set."""

    name = "agent"

    def __init__(self):
        self.state = AgentState()
        self.actions = {}

    def can_handle(self, action):
        return action in self.actions

    def handle(self, task, asset):
        handler = self.actions.get(task.get("action"))
        if handler is None:
            raise ValueError(
                "agent '{}' cannot handle action '{}'".format(
                    self.name, task.get("action")
                )
            )
        self.state.transition("RUNNING")
        try:
            result = handler(task, asset)
        except Exception:
            self.state.transition("FAILED")
            raise
        self.state.transition("SUCCESS")
        return result
