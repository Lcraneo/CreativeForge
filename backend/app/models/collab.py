from sqlalchemy import JSON, Column, DateTime, String

from app.models.base import Base, utcnow


class Project(Base):
    """Collaboration project (Phase 22.6): Organization -> Project ->
    Asset Library. `tenant_id` scopes the SaaS multi-tenant split (22.8)."""

    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False, default="default", index=True)
    owner_id = Column(String, nullable=False)
    description = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ProjectMember(Base):
    """Project membership with the Phase 22 role model:
    owner / designer / developer / reviewer."""

    __tablename__ = "project_members"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    role = Column(String, nullable=False, default="designer")
    created_at = Column(DateTime(timezone=True), default=utcnow)
