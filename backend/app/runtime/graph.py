"""DAG Task Graph Engine (Phase 16.13 / 17.4).

Real production is not linear: DNA and Motion can run in parallel after
AssetStruct, then converge on Combat before Export.

    Generate -> AssetStruct -> {DNA, Motion} -> Combat -> Export -> Quality

The Planner emits the graph; the Executor drives it with `next_tasks()`.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskNode:
    id: str
    agent: str
    input: list[str] = field(default_factory=list)
    output: list[str] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "input": self.input,
            "output": self.output,
            "status": self.status,
        }


class TaskGraph:
    def __init__(self, nodes: list[TaskNode], edges: list[tuple[str, str]]):
        self.nodes: dict[str, TaskNode] = {node.id: node for node in nodes}
        self.edges: list[tuple[str, str]] = list(edges)

    def dependents(self, node_id: str) -> list[str]:
        return [to for frm, to in self.edges if frm == node_id]

    def dependencies(self, node_id: str) -> list[str]:
        return [frm for frm, to in self.edges if to == node_id]

    def next_tasks(self, completed: set[str]) -> list[str]:
        """Nodes whose dependencies are all completed (or no dependencies)."""
        ready = []
        for node_id, node in self.nodes.items():
            if node.status == "done" or node_id in completed:
                continue
            deps = self.dependencies(node_id)
            if all(dep in completed for dep in deps):
                ready.append(node_id)
        return ready

    def mark(self, node_id: str, status: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [[frm, to] for frm, to in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskGraph":
        nodes = [
            TaskNode(
                id=node["id"],
                agent=node["agent"],
                input=node.get("input") or [],
                output=node.get("output") or [],
                status=node.get("status") or "pending",
            )
            for node in data.get("nodes", [])
        ]
        return cls(nodes, [tuple(edge) for edge in data.get("edges", [])])


def build_dag(tasks: list[str]) -> TaskGraph:
    """Canonical agent DAG for a task list.

    Supported chains (Phase 16.13):
      create: generate_asset -> structure_asset -> {create_dna, motion_align}
              -> combat -> gimport -> quality_check
      modify: find_character -> generate_asset -> ... (same tail)
    """
    nodes = [TaskNode(id=task, agent=AGENT_FOR_TASK.get(task, task)) for task in tasks]
    edges: list[tuple[str, str]] = []

    def link(sequence: list[str]) -> None:
        for frm, to in zip(sequence, sequence[1:]):
            edges.append((frm, to))

    head = [task for task in tasks if task not in CANON_TAIL and task not in ("create_dna", "motion_align")]
    tail = [task for task in CANON_TAIL if task in tasks]

    link(head)
    link(tail)
    parallel_branches = [t for t in tasks if t in ("create_dna", "motion_align")]
    if head and parallel_branches:
        for branch in parallel_branches:
            edges.append((head[-1], branch))
            if tail:
                edges.append((branch, tail[0]))
    elif parallel_branches and tail:
        for branch in parallel_branches:
            edges.append((branch, tail[0]))
    if not parallel_branches and head and tail:
        # linear chain: head must feed the tail (Phase 23 fix — short chains
        # like find -> modify_style -> quality were previously disconnected)
        edges.append((head[-1], tail[0]))
    return TaskGraph(nodes, edges)


CANON_TAIL = ["combat", "gimport", "quality_check"]


AGENT_FOR_TASK = {
    "find_character": "MemoryAgent",
    "modify_style": "StyleAgent",
    "generate_asset": "GenerateAgent",
    "structure_asset": "AssetStructAgent",
    "create_dna": "DNAAgent",
    "motion_align": "MotionAgent",
    "combat": "CombatAgent",
    "create_logic": "GameLogicAgent",
    "simulate": "SimulationAgent",
    "gimport": "ExportAgent",
    "quality_check": "QualityAgent",
}
