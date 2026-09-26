from typing import Any, Optional

from pydantic import BaseModel, Field


class TrainRequest(BaseModel):
    name: str = Field(default="dna_encoder", min_length=1)


class TrainResponse(BaseModel):
    report: dict[str, Any] = Field(default_factory=dict)


class EmbedRequest(BaseModel):
    image: str = Field(..., min_length=1, description="Image path / uri")


class EmbedResponse(BaseModel):
    image: str
    vector: list[float]
    dim: int
    model: str
    tier: str = "gpu"
    gpu: dict[str, Any] = Field(default_factory=dict)


class QualityCheckRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)


class QualityCheckResponse(BaseModel):
    asset_id: str
    scores: dict[str, Any] = Field(default_factory=dict)
    game_ready: Optional[float] = None


class MotionAnalyzeRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)


class MotionAnalyzeResponse(BaseModel):
    asset_id: str
    clips: list[dict[str, Any]] = Field(default_factory=list)
    tier: str = "gpu"


class RegistryResponse(BaseModel):
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class RunsResponse(BaseModel):
    runs: list[dict[str, Any]] = Field(default_factory=list)


class TiersResponse(BaseModel):
    tiers: dict[str, str] = Field(default_factory=dict)
