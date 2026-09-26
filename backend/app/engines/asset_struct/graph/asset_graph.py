"""Asset Graph (Phase 13.8): not just splitting an image, building the
asset relationship tree.

    Character
      |- Body
      |- Weapon
      |    \\- Sword
      \\- Effect
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssetNode:
    id: str
    type: str
    children: list["AssetNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "children": [child.to_dict() for child in self.children],
        }


class AssetGraphBuilder:
    def build(self, parts: list[dict[str, Any]]) -> AssetNode:
        root = AssetNode(id="character", type="character")
        for part in parts:
            node = AssetNode(id=part["name"], type=part["type"])
            if part["type"] == "weapon":
                # A weapon layer owns its sub-equipment (e.g. sword).
                node.children.append(AssetNode(id=f"{part['name']}_part", type="part"))
            root.children.append(node)
        return root

    def flatten(self, node: AssetNode, parent_id: str | None = None) -> list[dict[str, Any]]:
        rows = [{"id": node.id, "parent_id": parent_id, "type": node.type}]
        for child in node.children:
            rows.extend(self.flatten(child, parent_id=node.id))
        return rows
