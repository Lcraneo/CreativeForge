"""Agent Executor (Phase 17.5-7): drives the DAG, manages state, resumes
checkpoints, heals failures.

    Planner -> TaskGraph -> Executor -> Agent -> Tool -> Result

State machine (17.6):
    CREATED -> PLANNING -> RUNNING -> WAITING_REVIEW? -> COMPLETED
                                     -> FAILED -> (repair -> RUNNING)

Checkpointing (17.7): every completed node is committed; a paused or
failed task restarts from `completed` without redoing finished work.
"""

import asyncio
import json
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentTask, Asset
from app.engines.foundation.knowledge import (
    KnowledgeRetriever,
    build_knowledge_graph,
)
from app.runtime.agents.base import BaseAgent
from app.runtime.graph import TaskGraph
from app.runtime.healing import healing_plan
from app.runtime.intent import IntentAnalyzer
from app.runtime.memory import AgentMemory
from app.runtime.planner import planner_runtime
from app.runtime.review import review_points_for, review_type
from app.services.dna_service import get_services
from app.services.persist import persist_pipeline
from app.runtime.evaluation import (
    CONFIDENCE_FLOOR,
    confidence_from_summary,
    evaluate_task_result,
    low_confidence_nodes,
)
from app.runtime.tiers import tier_for


def build_agents() -> dict[str, BaseAgent]:
    from app.runtime.agents.combat import CombatAgent
    from app.runtime.agents.dna import DNAAgent
    from app.runtime.agents.export import ExportAgent
    from app.runtime.agents.generate import GenerateAgent
    from app.runtime.agents.logic import GameLogicAgent
    from app.runtime.agents.memory import MemoryAgent
    from app.runtime.agents.motion import MotionAgent
    from app.runtime.agents.quality import QualityAgent
    from app.runtime.agents.simulate import SimulationAgent
    from app.runtime.agents.struct import AssetStructAgent
    from app.runtime.agents.style import StyleAgent

    agents: list[BaseAgent] = [
        MemoryAgent(),
        StyleAgent(),
        GameLogicAgent(),
        SimulationAgent(),
        GenerateAgent(),
        AssetStructAgent(),
        DNAAgent(),
        MotionAgent(),
        CombatAgent(),
        ExportAgent(),
        QualityAgent(),
    ]
    return {agent.task: agent for agent in agents}


class AgentExecutor:
    def __init__(self, memory: AgentMemory | None = None):
        self.memory = memory or AgentMemory()
        self.agents = build_agents()

    # -- entry points -------------------------------------------------------

    async def run_task(
        self,
        goal: str,
        db: AsyncSession,
        user_id: str = "anonymous",
        engine: str | None = None,
        review: bool | list[str] | None = False,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        row = AgentTask(id=task_id, user_id=user_id, goal=goal, status="PLANNING")
        db.add(row)
        await db.commit()

        intent = IntentAnalyzer().analyze(goal)
        preferences = await self.memory.recall_preferences(db, user_id)
        plan = planner_runtime.create_plan(goal, intent, preferences)
        if engine:
            plan["engine"] = engine
        if provider:
            plan["image_provider"] = provider
        if model:
            plan["image_model"] = model
        row.plan = plan
        row.status = "RUNNING"
        await db.commit()

        # user preference memory (Phase 17.8 layer 2)
        await self.memory.remember_preference(db, user_id, "style", intent["style"])
        if plan.get("engine"):
            await self.memory.remember_preference(db, user_id, "engine", plan["engine"])

        services = get_services()
        await services.hydrate(db)

        # Phase 23.2: Knowledge Retriever — graph facts + metadata context
        asset_rows = (
            await db.execute(
                select(Asset).order_by(Asset.created_at.desc()).limit(50)
            )
        ).scalars().all()
        knowledge_graph = build_knowledge_graph(
            [row.metadata_json or {} for row in asset_rows]
        )
        knowledge = KnowledgeRetriever(knowledge_graph).context_for(goal)

        context: dict[str, Any] = {
            "goal": goal,
            "db": db,
            "services": services,
            "plan": plan,
            "intent": intent,
            "request": {"engine": engine, "provider": provider, "model": model},
            "knowledge": knowledge,
            "user_id": user_id,
        }
        graph = TaskGraph.from_dict(plan["dag"])
        return await self._drive(
            row, graph, context, [], set(), {}, db, review_points_for(review)
        )

    async def resume(self, task_id: str, db: AsyncSession) -> dict[str, Any]:
        """Continue a WAITING_REVIEW task from its checkpoint (Phase 17.7)."""
        row = await db.get(AgentTask, task_id)
        if row is None:
            raise ValueError(f"task not found: {task_id}")
        if row.status != "WAITING_REVIEW":
            return self._snapshot(row)

        checkpoint = row.checkpoint or {}
        plan = row.plan or {}
        services = get_services()
        await services.hydrate(db)

        context: dict[str, Any] = {
            "goal": row.goal,
            "db": db,
            "services": services,
            "plan": plan,
            "intent": plan.get("intent"),
            "request": {
                "engine": plan.get("engine"),
                "provider": plan.get("image_provider"),
                "model": plan.get("image_model"),
            },
            "user_id": row.user_id,
            "asset": checkpoint.get("asset"),
            "character": checkpoint.get("character"),
            "changes": checkpoint.get("changes"),
            "dna": checkpoint.get("dna"),
            "version": checkpoint.get("version"),
        }
        approved = list(checkpoint.get("approved") or [])
        pending = checkpoint.get("review_pending")
        if pending and pending not in approved:
            approved.append(pending)
        row.checkpoint = {**checkpoint, "approved": approved}
        row.status = "RUNNING"
        await db.commit()

        graph = TaskGraph.from_dict(plan.get("dag") or {"nodes": [], "edges": []})
        return await self._drive(
            row,
            graph,
            context,
            row.steps or [],
            set(checkpoint.get("completed") or []),
            row.result or {},
            db,
            [],
        )

    # -- core loop ------------------------------------------------------------

    async def _drive(
        self,
        row: AgentTask,
        graph: TaskGraph,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
        completed: set[str],
        result: dict[str, Any],
        db: AsyncSession,
        review_points: list[str],
    ) -> dict[str, Any]:
        repair_rounds = 0
        selfeval_rounds = 0
        while True:
            ready = graph.next_tasks(completed)
            if not ready:
                break

            for node in ready:
                graph.mark(node, "running")
                row.current_node = node
            await db.commit()

            outcomes = await asyncio.gather(
                *[self._invoke_agent(node, context) for node in ready],
                return_exceptions=True,
            )

            pause_now = False
            for node, outcome in zip(ready, outcomes):
                if isinstance(outcome, Exception):
                    healed = await self._retry_node(node, outcome, graph, context, steps, row, db)
                    if healed is None:
                        return await self._fail(
                            row, f"{node} failed after heal attempt: {outcome}", result, db
                        )
                    # the healed step is already recorded by _run_node
                    summary, elapsed = healed, 0.0
                else:
                    summary, elapsed = outcome
                    self._record_step(node, self.agents.get(node), steps, summary, elapsed)
                    self.memory.process.record(node, elapsed, True)
                graph.mark(node, "done")
                completed.add(node)
                result[node] = summary

                if node in review_points and node not in (row.checkpoint or {}).get(
                    "approved", []
                ):
                    pause_now = True

            row.steps = list(steps)
            await db.commit()

            if pause_now:
                pending = next(
                    (n for n in ready if n in review_points), ready[0]
                )
                return await self._pause(
                    row, pending, graph, completed, result, steps, context, db
                )

            # Phase 22.4: self evaluation — rerun low-confidence nodes once.
            low = low_confidence_nodes(result)
            if low and selfeval_rounds < 1:
                selfeval_rounds += 1
                steps.append(
                    {
                        "node": "self_evaluation",
                        "agent": "QualityAgent",
                        "status": "healing",
                        "ms": 0.0,
                        "tier": tier_for("quality_check"),
                        "summary": {"low_confidence": low, "floor": CONFIDENCE_FLOOR},
                    }
                )
                row.steps = list(steps)
                await db.commit()
                for node_id in low:
                    graph.mark(node_id, "pending")
                    completed.discard(node_id)
                    result.pop(node_id, None)
                continue

            verdict = result.get("quality_check")
            if isinstance(verdict, dict) and verdict.get("passed") is False:
                if repair_rounds >= 1:
                    return await self._fail(
                        row,
                        "quality gate: " + json.dumps(verdict.get("issues", [])),
                        result,
                        db,
                    )
                repair_rounds += 1
                issues = verdict.get("issues") or []
                steps.append(
                    {
                        "node": "quality_check",
                        "agent": "QualityAgent",
                        "status": "healing",
                        "ms": 0.0,
                        "tier": tier_for("quality_check"),
                        "summary": {"issues": issues},
                    }
                )
                row.steps = list(steps)
                await db.commit()
                for node_id in healing_plan(issues) + ["quality_check"]:
                    graph.mark(node_id, "pending")
                    completed.discard(node_id)
                    result.pop(node_id, None)
                continue

        # Phase 23.10: every task ships with an evaluation record — the
        # feedback loop's data point (identity / animation / engine).
        result["evaluation"] = evaluate_task_result(context.get("asset") or {})
        asset_id = await persist_pipeline(db, context, row.id, row.plan or {}, result)
        row.status = "COMPLETED"
        row.current_node = None
        row.steps = list(steps)
        row.result = dict(result)
        row.checkpoint = {}
        row.asset_id = asset_id
        await db.commit()
        return {
            "task_id": row.id,
            "status": "completed",
            "plan": row.plan,
            "result": result,
            "asset_id": asset_id,
            "asset": context.get("asset") or {},
        }

    async def _run_node(
        self,
        node_id: str,
        graph: TaskGraph,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
        row: AgentTask,
        db: AsyncSession,
    ) -> dict[str, Any]:
        agent = self.agents.get(node_id)
        graph.mark(node_id, "running")
        row.current_node = node_id
        await db.commit()

        summary, elapsed = await self._invoke_agent(node_id, context)
        self._record_step(node_id, agent, steps, summary, elapsed)
        row.steps = list(steps)
        self.memory.process.record(node_id, elapsed, True)
        await db.commit()
        return summary

    async def _invoke_agent(
        self, node_id: str, context: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """Session-free invocation: safe inside asyncio.gather (Phase 17.5)."""
        agent = self.agents.get(node_id)
        started = time.perf_counter()
        if agent is None:
            summary: dict[str, Any] = {"status": "skipped", "reason": "no agent registered"}
        else:
            summary = await agent.run(context)
        if isinstance(summary, dict):
            # Phase 22.4: agents self-evaluate; the executor just records it.
            summary.setdefault("confidence", confidence_from_summary(node_id, summary))
        return summary, round((time.perf_counter() - started) * 1000, 2)

    @staticmethod
    def _record_step(
        node_id: str,
        agent: BaseAgent | None,
        steps: list[dict[str, Any]],
        summary: dict[str, Any],
        elapsed: float,
    ) -> None:
        steps.append(
            {
                "node": node_id,
                "agent": agent.name if agent else "-",
                "status": "done",
                "ms": elapsed,
                "tier": tier_for(node_id),
                "summary": summary,
            }
        )

    async def _retry_node(
        self,
        node_id: str,
        exc: Exception,
        graph: TaskGraph,
        context: dict[str, Any],
        steps: list[dict[str, Any]],
        row: AgentTask,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """One self-healing retry (Phase 17.11); None means still failing."""
        steps.append(
            {
                "node": node_id,
                "agent": self.agents[node_id].name if node_id in self.agents else "-",
                "status": "failed",
                "ms": 0.0,
                "tier": tier_for(node_id),
                "summary": {"error": str(exc)[:300]},
            }
        )
        row.steps = list(steps)
        self.memory.process.record(node_id, 0.0, False)
        await db.commit()

        graph.mark(node_id, "pending")
        try:
            summary = await self._run_node(node_id, graph, context, steps, row, db)
            steps[-1]["status"] = "healed"
            row.steps = list(steps)
            await db.commit()
            return summary
        except Exception:
            return None

    # -- terminal states --------------------------------------------------

    async def _pause(
        self,
        row: AgentTask,
        node: str,
        graph: TaskGraph,
        completed: set[str],
        result: dict[str, Any],
        steps: list[dict[str, Any]],
        context: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        row.status = "WAITING_REVIEW"
        row.current_node = node
        row.steps = list(steps)
        row.result = dict(result)
        row.checkpoint = {
            "asset": context.get("asset"),
            "character": context.get("character"),
            "changes": context.get("changes"),
            "dna": context.get("dna"),
            "version": context.get("version"),
            "completed": sorted(completed),
            "review_pending": node,
        }
        await db.commit()
        return {
            "task_id": row.id,
            "status": "waiting_review",
            "plan": row.plan,
            "result": result,
            "asset_id": None,
            "asset": None,
            "review": {"point": node, "type": review_type(node)},
        }

    async def _fail(
        self, row: AgentTask, error: str, result: dict[str, Any], db: AsyncSession
    ) -> dict[str, Any]:
        row.status = "FAILED"
        row.error = error[:500]
        row.result = dict(result)
        row.current_node = None
        await db.commit()
        return {
            "task_id": row.id,
            "status": "failed",
            "plan": row.plan,
            "result": result,
            "asset_id": None,
            "asset": None,
            "error": error,
        }

    def _snapshot(self, row: AgentTask) -> dict[str, Any]:
        return {
            "task_id": row.id,
            "status": (row.status or "").lower(),
            "plan": row.plan,
            "result": row.result,
            "asset_id": row.asset_id,
            "asset": None,
            "error": row.error,
        }


_executor: AgentExecutor | None = None


def get_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        _executor = AgentExecutor()
    return _executor
