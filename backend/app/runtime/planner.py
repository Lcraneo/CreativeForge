"""Planner Runtime (Phase 16.4-5 / 17.3 / 22.1): a dynamic decision system.

Responsibilities:
  1. Goal understanding   (delegates to the Intent Analyzer)
  2. Capability matching  (MCP-style tool schemas from the registry)
  3. Plan generation      (task chain + DAG + recorded decisions)

Not a fixed pipeline (Phase 22 Dynamic Planner): the modification's change
type picks the chain — a style-only edit runs the minimal
`find_character -> modify_style -> quality_check` chain and reuses the
previous version's animation/combat/engine payload, while weapon or motion
edits regenerate through the full identity-preserving pipeline. The
planner records WHY it chose the path so the execution trace is legible.
"""

from typing import Any

from app.runtime.graph import AGENT_FOR_TASK, build_dag
from app.runtime.intent import IntentAnalyzer
from app.runtime.registry import TOOL_SCHEMAS

CREATE_TASKS = ["generate_asset", "structure_asset", "create_dna", "motion_align", "gimport"]
MODIFY_TASKS = ["find_character", *CREATE_TASKS]
STYLE_EDIT_TASKS = ["find_character", "modify_style"]
SKILL_EDIT_TASKS = ["find_character", "create_logic", "simulate", "gimport"]

MODE_BY_INTENT = {
    "character_modification": "modify_existing_character",
    "game_character_creation": "create_character",
}


class PlannerRuntime:
    name = "PlannerRuntime"

    def __init__(self, analyzer: IntentAnalyzer | None = None):
        self.analyzer = analyzer or IntentAnalyzer()

    def create_plan(
        self,
        goal: str,
        intent: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent = intent or self.analyzer.analyze(goal)
        decisions: list[str] = [f"intent: {intent['type']}"]

        mode = MODE_BY_INTENT[intent["type"]]
        change = intent.get("change")
        tasks = list(MODIFY_TASKS if mode == "modify_existing_character" else CREATE_TASKS)
        extra_tail = ["combat"]
        if mode == "modify_existing_character" and change == "style":
            # Phase 22 Dynamic Planner: a style edit carries the previous
            # version's layers/animation/combat/engine payload — regenerating
            # them would waste work and risk identity drift.
            tasks = list(STYLE_EDIT_TASKS)
            extra_tail = []
            decisions.append(
                "change=style -> minimal chain (motion/combat reused from previous version)"
            )
        elif mode == "modify_existing_character" and change == "skill":
            # Phase 23: a skill addition generates game logic + simulation
            # instead of regenerating the artwork; the engine package is
            # re-exported so the new skill reaches the game.
            tasks = list(SKILL_EDIT_TASKS)
            extra_tail = []
            decisions.append(
                "change=skill -> logic chain (GameLogicAgent + SimulationAgent, re-export)"
            )

        engine = intent.get("engine")
        if not engine and preferences and preferences.get("engine"):
            engine = preferences["engine"]
            decisions.append(f"engine from user preference: {engine}")
        if intent.get("style") and intent["style"] != "anime":
            decisions.append(f"style locked to {intent['style']}")

        # Capability matching: every planned task must exist in the registry.
        capabilities = [TOOL_SCHEMAS[t]["name"] for t in tasks if t in TOOL_SCHEMAS]
        missing = [t for t in tasks if t not in TOOL_SCHEMAS and t != "find_character"]
        if missing:
            decisions.append(f"unregistered capabilities skipped: {missing}")

        dag = build_dag(tasks + extra_tail + ["quality_check"])
        return {
            "goal": goal,
            "mode": mode,
            "change": change,
            "intent": intent,
            "tasks": tasks,
            "engine": engine,
            "decisions": decisions,
            "capabilities": capabilities,
            "agents": sorted(
                {AGENT_FOR_TASK[t] for t in tasks + extra_tail + ["quality_check"]}
            ),
            "dag": dag.to_dict(),
        }


planner_runtime = PlannerRuntime()
