"""Game Asset Knowledge Graph + RAG (Phase 23.1-4).

The layer that lets agents reason about *relations*, not just images:

    Character --HAS_WEAPON--> Weapon --TRIGGERS--> Skill --NEEDS--> Animation
    Character --HAS_STYLE--> Style        Skill --HAS_BLUEPRINT--> LogicSkill
    Character --EXPORTED_TO--> Engine

`build_knowledge_graph` mines the asset library (CreativeAsset metadata)
into nodes/edges; `KnowledgeRetriever.context_for(goal)` combines relation
facts with DNA metadata search into the context pack the GameLogicAgent
consumes (the vector leg plugs in with the real text encoder).
"""

from typing import Any

Node = dict[str, Any]
Edge = tuple[str, str, str]  # (src_id, relation, dst_id)


class KnowledgeGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def add_node(self, type_: str, label: str, **attrs: Any) -> str:
        node_id = f"{type_}:{label}"
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "type": type_, "label": label}
        self.nodes[node_id].update({k: v for k, v in attrs.items() if v is not None})
        return node_id

    def add_edge(self, src: str, relation: str, dst: str) -> None:
        edge = (src, relation, dst)
        if edge not in self.edges:
            self.edges.append(edge)

    def facts_about(self, node_id: str) -> list[dict[str, str]]:
        facts = []
        for src, rel, dst in self.edges:
            if src == node_id:
                facts.append({"src": src, "relation": rel, "dst": dst})
            elif dst == node_id:
                facts.append({"src": src, "relation": f"INV_{rel}", "dst": dst})
        return facts

    def by_type(self, type_: str) -> list[Node]:
        return [n for n in self.nodes.values() if n["type"] == type_]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes.values()),
            "edges": [
                {"src": src, "relation": rel, "dst": dst} for src, rel, dst in self.edges
            ],
        }


def _first(layers: list[dict[str, Any]], type_: str) -> dict[str, Any] | None:
    return next((l for l in layers if l.get("type") == type_ or l.get("name") == type_), None)


def build_knowledge_graph(assets: list[dict[str, Any]]) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for asset in assets:
        identity = asset.get("identity") or {}
        name = identity.get("name") or "character"
        character = graph.add_node("character", name, species=identity.get("species"))

        style = (asset.get("style") or {}).get("name")
        if style:
            graph.add_edge(character, "HAS_STYLE", graph.add_node("style", style))

        layers = (asset.get("content") or {}).get("layers") or []
        weapon_layer = _first(layers, "weapon")
        weapon_label = (weapon_layer or {}).get("name")
        if weapon_label:
            weapon = graph.add_node("weapon", weapon_label)
            graph.add_edge(character, "HAS_WEAPON", weapon)

        for clip in (asset.get("animation") or {}).get("clips") or []:
            animation = graph.add_node("animation", str(clip.get("name")))
            graph.add_edge(character, "HAS_ANIMATION", animation)

        for skill in (asset.get("combat") or {}).get("skills") or []:
            skill_name = str(skill.get("skill") or "skill")
            skill_node = graph.add_node(
                "skill",
                skill_name,
                damage=skill.get("damage"),
                element=skill.get("element"),
            )
            source = weapon or character
            graph.add_edge(source, "TRIGGERS", skill_node)
            if skill.get("animation"):
                graph.add_edge(
                    skill_node, "NEEDS", graph.add_node("animation", str(skill["animation"]))
                )

        for blueprint in (asset.get("logic") or {}).get("skills") or []:
            bp_name = str(blueprint.get("name") or "blueprint")
            blueprint_node = graph.add_node(
                "logic_skill",
                bp_name,
                cooldown=(blueprint.get("trigger") or {}).get("cooldown"),
                damage=blueprint.get("damage"),
            )
            graph.add_edge(character, "HAS_SKILL", blueprint_node)

        target = (asset.get("engine") or {}).get("target")
        if target:
            graph.add_edge(character, "EXPORTED_TO", graph.add_node("engine", str(target)))
    return graph


class KnowledgeRetriever:
    """Graph + metadata context pack for a goal (Phase 23.2)."""

    TYPE_HINTS = (
        ("weapon", ("剑", "刀", "枪", "武器")),
        ("skill", ("技能", "skill")),
        ("animation", ("动画", "动作")),
        ("engine", ("cocos", "unity", "godot")),
    )

    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph

    def context_for(self, goal: str) -> dict[str, Any]:
        lowered = (goal or "").lower()
        entities = [
            node
            for node in self.graph.nodes.values()
            if node["label"] and node["label"].lower() in lowered
        ]
        wanted_types = [
            type_ for type_, keys in self.TYPE_HINTS if any(k in lowered for k in keys)
        ]
        for type_ in wanted_types:
            entities.extend(node for node in self.graph.by_type(type_) if node not in entities)

        facts: list[dict[str, str]] = []
        for node in entities:
            facts.extend(self.graph.facts_about(node["id"]))
        return {
            "entities": [node["id"] for node in entities],
            "facts": facts,
            "graph_size": {"nodes": len(self.graph.nodes), "edges": len(self.graph.edges)},
        }
