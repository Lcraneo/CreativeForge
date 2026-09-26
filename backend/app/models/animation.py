from sqlalchemy import JSON, Column, Float, Integer, String

from app.models.base import Base


class AnimationClip(Base):
    """Animation timeline record (Phase 15.3)."""

    __tablename__ = "animation_clips"

    id = Column(String, primary_key=True)
    character_id = Column(String, index=True)
    name = Column(String, nullable=False)
    duration = Column(Float, default=0.0)
    fps = Column(Integer, default=12)
    metadata_json = Column(JSON, default=dict)


class AnimationEvent(Base):
    """Frame-bound gameplay event (Phase 15.3 / 15.5)."""

    __tablename__ = "animation_events"

    id = Column(String, primary_key=True)
    animation_id = Column(String, nullable=False, index=True)
    frame = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, default=dict)


class AnimationState(Base):
    """Animation state machine entry (Phase 15.3)."""

    __tablename__ = "animation_states"

    id = Column(String, primary_key=True)
    character_id = Column(String, index=True)
    state = Column(String, nullable=False)
    clip_id = Column(String)
    transition = Column(JSON, default=dict)
