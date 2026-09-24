class AgentMessage:
    """Unified inter-agent message (from / to / type / payload)."""

    TYPES = (
        "TASK_ASSIGN",
        "TASK_RESULT",
        "ASSET_READY",
        "QUALITY_REPORT",
        "RECOVERY_REQUEST"
    )

    def __init__(self, sender, receiver, type, payload=None):
        self.sender = sender
        self.receiver = receiver
        self.type = type
        self.payload = payload if payload is not None else {}

    def to_dict(self):
        return {
            "from": self.sender,
            "to": self.receiver,
            "type": self.type,
            "payload": self.payload
        }


class MessageBus:
    """In-memory message routing between registered agents."""

    def __init__(self):
        self._inboxes = {}
        self.history = []

    def register(self, agent_name):
        self._inboxes.setdefault(agent_name, [])

    def send(self, message):
        self.history.append(message.to_dict())
        self._inboxes.setdefault(message.receiver, []).append(message)

    def receive(self, agent_name):
        messages = self._inboxes.get(agent_name, [])
        self._inboxes[agent_name] = []
        return messages
