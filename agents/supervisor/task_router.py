class TaskRouter:
    """Routes tasks to registered agents and dispatches them."""

    def __init__(self):
        self.agents = {}

    def register(self, agent):
        self.agents[agent.name] = agent

    def route(self, task):
        agent = self.agents.get(task.get("agent"))
        if agent is None:
            raise LookupError("no agent registered as '{}'".format(task.get("agent")))
        if not agent.can_handle(task.get("action")):
            raise ValueError(
                "agent '{}' cannot handle action '{}'".format(task.get("agent"), task.get("action"))
            )
        return agent

    def dispatch(self, task, asset):
        agent = self.route(task)
        return agent.handle(task, asset)
