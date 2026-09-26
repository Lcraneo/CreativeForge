from typing import Optional

from app.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)

    def names(self) -> list[str]:
        return sorted(self.tools)


registry = ToolRegistry()


def register_default_tools() -> ToolRegistry:
    """Register the built-in pipeline tools (idempotent)."""
    from app.tools.dna_tool import DnaTool
    from app.tools.generate_tool import GenerateTool
    from app.tools.gimport_tool import GImportTool
    from app.tools.motion_tool import MotionAlignTool
    from app.tools.search_tool import CharacterSearchTool
    from app.tools.struct_tool import StructTool

    for tool in (
        GenerateTool(),
        CharacterSearchTool(),
        StructTool(),
        DnaTool(),
        MotionAlignTool(),
        GImportTool(),
    ):
        registry.register(tool)
    return registry
