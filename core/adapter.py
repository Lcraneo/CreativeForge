from abc import ABC, abstractmethod


class AssetAdapter(ABC):

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def version(self) -> str:
        pass

    @abstractmethod
    def can_handle(self, asset_type: str) -> bool:
        pass

    @abstractmethod
    def import_asset(self, source):
        pass

    @abstractmethod
    def export_asset(self, asset):
        pass
