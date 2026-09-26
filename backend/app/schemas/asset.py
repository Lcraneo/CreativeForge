from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AssetCreateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural language goal")
    engine: Optional[str] = Field(
        None, description="Engine target override (unity / cocos / godot)"
    )
    review: bool | list[str] = Field(
        False,
        description="Human review points (Phase 17.10): True = concept review, "
        "or a list of node ids",
    )
    user_id: str = Field("anonymous", description="Owner for preference memory")


class AssetCreateResponse(BaseModel):
    task_id: str
    status: str
    plan: dict[str, Any]
    result: dict[str, Any]
    asset_id: Optional[str] = None
    review: Optional[dict[str, Any]] = None


class AssetSummary(BaseModel):
    id: str
    name: str
    asset_type: str
    status: str
    created_at: Optional[datetime] = None


class AssetDetail(AssetSummary):
    project_id: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    """Phase 18.10: re-export an existing asset to another engine."""

    asset_id: str
    engine: Optional[str] = Field(None, description="unity / cocos / godot")


class ExportResponse(BaseModel):
    asset_id: str
    engine: str
    root: str
    files: list[str]
    quality: dict[str, Any]
