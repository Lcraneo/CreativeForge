class AdapterRegistry:

    def __init__(self):
        self.adapters = []

    def register(self, adapter):
        self.adapters.append(adapter)

    def find(self, capability):
        for adapter in self.adapters:
            if adapter.can_handle(capability):
                return adapter
        return None
