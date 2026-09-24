AGENT_STATES = ("CREATED", "RUNNING", "SUCCESS", "FAILED", "RECOVERY")


class AgentState:
    """Agent lifecycle state machine with transition history."""

    def __init__(self):
        self.state = "CREATED"
        self.history = ["CREATED"]

    def transition(self, state):
        if state not in AGENT_STATES:
            raise ValueError(
                "invalid agent state '{}', expected one of {}".format(
                    state, AGENT_STATES
                )
            )
        self.state = state
        self.history.append(state)

    def to_dict(self):
        return {
            "state": self.state,
            "history": list(self.history)
        }
