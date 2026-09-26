"""Task API (Phase 17/18): agent task records with execution traces.

Reads both the runtime `agent_tasks` table (Phase 17) and the Phase 11
`tasks` table, so records from either era are visible. Approval resumes a
WAITING_REVIEW task from its checkpoint (Phase 17.7 + 17.10).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import AgentTask, Task
from app.runtime.gateway import get_gateway
from app.schemas.task import ApproveResponse, TaskResponse

router = APIRouter()


def _from_agent_task(row: AgentTask) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        goal=row.goal,
        status=(row.status or "CREATED").lower(),
        plan=row.plan,
        result=row.result,
        created_at=row.created_at,
        current_node=row.current_node,
        steps=row.steps,
        asset_id=row.asset_id,
        error=row.error,
        source="agent_task",
    )


def _from_task(row: Task) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        goal=row.goal,
        status=row.status or "pending",
        plan=row.plan,
        result=row.result,
        created_at=row.created_at,
        source="task",
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(limit: int = 20, db: AsyncSession = Depends(get_db)):
    agent_rows = (
        await db.execute(
            select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
        )
    ).scalars()
    items = [_from_agent_task(row) for row in agent_rows]
    remaining = max(0, limit - len(items))
    if remaining:
        rows = (
            await db.execute(
                select(Task).order_by(Task.created_at.desc()).limit(remaining)
            )
        ).scalars()
        items.extend(_from_task(row) for row in rows)
    return items


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(AgentTask, task_id)
    if row is not None:
        return _from_agent_task(row)
    legacy = await db.get(Task, task_id)
    if legacy is not None:
        return _from_task(legacy)
    raise HTTPException(status_code=404, detail="task not found")


@router.post("/{task_id}/approve", response_model=ApproveResponse)
async def approve_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Human review approval (Phase 17.10): resume from the checkpoint."""
    row = await db.get(AgentTask, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    if row.status != "WAITING_REVIEW":
        raise HTTPException(
            status_code=409,
            detail=f"task is not waiting for review (status={row.status})",
        )
    result = await get_gateway().approve(task_id, db)
    return ApproveResponse(
        task_id=task_id,
        status=result.get("status", "unknown"),
        asset_id=result.get("asset_id"),
        detail=(result.get("error") or "") or None,
    )
