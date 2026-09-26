from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    goal: str
    status: str
    plan: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    # Phase 17/18: agent execution trace
    current_node: Optional[str] = None
    steps: Optional[list[dict[str, Any]]] = None
    asset_id: Optional[str] = None
    error: Optional[str] = None
    source: str = "task"


class ApproveResponse(BaseModel):
    task_id: str
    status: str
    asset_id: Optional[str] = None
    detail: Optional[str] = None
