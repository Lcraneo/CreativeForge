from sqlalchemy import JSON, Column, DateTime, String

from app.models.base import Base, utcnow


class AgentTask(Base):
    """Agent Runtime task record (Phase 17.6 / 18.13).

    Lifecycle: CREATED -> PLANNING -> RUNNING -> WAITING_REVIEW?
              -> COMPLETED | FAILED -> (RETRY -> RUNNING)

    `checkpoint` holds the shared pipeline context snapshot so a paused or
    failed task can resume without redoing completed nodes (Phase 17.7).
    """

    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, default="anonymous")
    goal = Column(String, nullable=False)
    status = Column(String, default="CREATED")
    current_node = Column(String)
    plan = Column(JSON)
    steps = Column(JSON, default=list)
    result = Column(JSON, default=dict)
    checkpoint = Column(JSON, default=dict)
    asset_id = Column(String)
    error = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserPreference(Base):
    """User preference memory (Phase 17.8 layer 2 / 16.12)."""

    __tablename__ = "user_preferences"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
