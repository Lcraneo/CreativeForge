"""Asset service (Phase 11.10 -> 16/17): API -> Task Gateway -> Agent Runtime.

The linear Phase 11 tool chain became the Phase 16-17 agent runtime
(Planner -> DAG -> domain agents -> Quality -> healing); the return
contract is unchanged: task_id / plan / result / asset_id / asset.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.gateway import get_gateway


async def create_asset(
    goal: str,
    db: AsyncSession,
    engine: str | None = None,
    review: bool | list[str] | None = False,
    user_id: str = "anonymous",
) -> dict[str, Any]:
    return await get_gateway().submit(
        goal, db, user_id=user_id, engine=engine, review=review
    )
