from sqlalchemy import JSON, Column, DateTime, String

from app.models.base import Base, utcnow


class Task(Base):
    """Agent execution record (Phase 11.6): plan, status and results."""

    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    goal = Column(String, nullable=False)
    status = Column(String, default="pending")
    plan = Column(JSON)
    result = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=utcnow)
