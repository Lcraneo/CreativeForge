from typing import Any, Optional

from pydantic import BaseModel, Field


class DnaCreateRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)


class DnaCreateResponse(BaseModel):
    character_id: str


class DnaResponse(BaseModel):
    character_id: str
    identity: dict[str, Any] = Field(default_factory=dict)
    embedding: dict[str, Any] = Field(default_factory=dict)
    versions: list[str] = Field(default_factory=list)


class DnaSearchRequest(BaseModel):
    image: str = Field(..., min_length=1, description="Image path / uri")


class DnaSearchResponse(BaseModel):
    match: Optional[str] = None
    score: float = 0.0
    is_same_character: bool = False
    character: Optional[dict[str, Any]] = None
