"""Task Gateway (Phase 17.2): the single entry for user goals.

Receives a natural language goal, turns it into a runtime task, hands it
to the executor and supports review approvals.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.runtime.executor import get_executor


class TaskGateway:
    async def submit(
        self,
        goal: str,
        db: AsyncSession,
        user_id: str = "anonymous",
        engine: str | None = None,
        review: bool | list[str] | None = False,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        return await get_executor().run_task(
            goal,
            db,
            user_id=user_id,
            engine=engine,
            review=review,
            provider=provider,
            model=model,
        )

    async def approve(self, task_id: str, db: AsyncSession) -> dict[str, Any]:
        return await get_executor().resume(task_id, db)


_gateway: TaskGateway | None = None


def get_gateway() -> TaskGateway:
    global _gateway
    if _gateway is None:
        _gateway = TaskGateway()
    return _gateway
