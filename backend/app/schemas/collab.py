from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    owner_id: str = Field(..., min_length=1)
    tenant_id: str = "default"


class MemberAddRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(..., pattern="^(owner|designer|developer|reviewer)$")


class AssetAttachRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)


class TransitionRequest(BaseModel):
    action: str = Field(..., pattern="^(submit|approve|promote)$")
    user_id: str = Field(..., min_length=1)


class TransitionResponse(BaseModel):
    asset_id: str
    status: str
    action: str


class MemberOut(BaseModel):
    user_id: str
    role: str


class AssetStateOut(BaseModel):
    id: str
    name: str
    status: str


class ProjectOut(BaseModel):
    id: str
    name: str
    tenant_id: str
    owner_id: str
    members: list[MemberOut] = Field(default_factory=list)
    assets: list[AssetStateOut] = Field(default_factory=list)


class ProjectSummary(BaseModel):
    id: str
    name: str
    tenant_id: str
    owner_id: str
