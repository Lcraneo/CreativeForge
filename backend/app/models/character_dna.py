from sqlalchemy import JSON, Column, DateTime, String

from app.models.base import Base, utcnow


class CharacterDna(Base):
    """Character DNA record: semantic + visual identity (Phase 14)."""

    __tablename__ = "character_dnas"

    character_id = Column(String, primary_key=True)
    identity = Column(JSON, default=dict)
    image_stem = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CharacterEmbedding(Base):
    """Identity vector storage (Phase 14.6)."""

    __tablename__ = "character_embeddings"

    id = Column(String, primary_key=True)
    character_id = Column(String, nullable=False, index=True)
    embedding = Column(JSON, nullable=False)
    model = Column(String, default="clip-mock-v1")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class CharacterVersion(Base):
    """Version graph node: characters evolve, never overwrite (Phase 14.9)."""

    __tablename__ = "character_versions"

    id = Column(String, primary_key=True)
    character_id = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False, default="v1")
    parent_version = Column(String, nullable=True)
    changes = Column(JSON, default=dict)
    asset_id = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow)
