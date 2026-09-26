"""Self Healing (Phase 16.16 / 17.11): what separates an agent from a workflow.

Quality issues map to concrete repair actions; the executor reruns the
offending agents and re-checks — one repair round, then it reports failure
instead of looping forever.
"""

from typing import Any

SUGGESTION_TO_NODE = {
    "rerun_structure": "structure_asset",
    "rerun_dna": "create_dna",
    "rerun_motion": "motion_align",
    "rerun_export": "gimport",
}


def healing_plan(issues: list[dict[str, Any]]) -> list[str]:
    """Quality issues -> ordered list of nodes to rerun."""
    nodes: list[str] = []
    for issue in issues:
        node = SUGGESTION_TO_NODE.get(issue.get("suggestion"))
        if node and node not in nodes:
            nodes.append(node)
    return nodes
