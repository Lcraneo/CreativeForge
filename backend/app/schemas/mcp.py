from typing import Any, Optional

from pydantic import BaseModel, Field


class McpInvokeRequest(BaseModel):
    tool: str = Field(..., min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class McpInvokeResponse(BaseModel):
    tool: str
    result: dict[str, Any] = Field(default_factory=dict)
