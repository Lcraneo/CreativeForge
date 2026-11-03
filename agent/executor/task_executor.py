from agent.capability.capability_registry import build_default_registry


class TaskExecutor:
    """Task -> Capability Registry -> Processor -> CreativeAsset update."""

    def __init__(self, registry=None):
        self.registry = registry or build_default_registry()

    def execute(self, task, asset):
        capability = self.registry.find(task.get("capability"))
        if capability is None:
            raise LookupError("no capability registered for '{}'".format(task.get("capability")))
        if capability.handler is None:
            raise LookupError("capability '{}' has no handler".format(capability.name))
        return capability.handler(asset, task)
