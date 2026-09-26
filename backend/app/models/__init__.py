"""Every model module is imported here so create_all sees all tables."""

from app.models.animation import AnimationClip, AnimationEvent, AnimationState
from app.models.asset import Asset
from app.models.asset_struct import AssetLayer, AssetNode
from app.models.base import Base, utcnow
from app.models.character_dna import (
    CharacterDna,
    CharacterEmbedding,
    CharacterVersion,
)
from app.models.collab import Project, ProjectMember
from app.models.runtime import AgentTask, UserPreference
from app.models.task import Task
from app.models.training import ModelArtifact, TrainingRun

__all__ = [
    "AgentTask",
    "AnimationClip",
    "AnimationEvent",
    "AnimationState",
    "Asset",
    "AssetLayer",
    "AssetNode",
    "Base",
    "CharacterDna",
    "CharacterEmbedding",
    "CharacterVersion",
    "ModelArtifact",
    "Project",
    "ProjectMember",
    "Task",
    "TrainingRun",
    "UserPreference",
    "utcnow",
]
