from sqlalchemy import JSON, Column, DateTime, String

from app.models.base import Base, utcnow


class Asset(Base):
    """A CreativeAsset persisted row (Phase 11.6).

    The full CreativeAsset contract dict lives in `metadata_json`; scalar
    columns exist for the fields the API queries and joins on.
    """

    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, default="default")
    name = Column(String, nullable=False)
    asset_type = Column(String, default="character")
    status = Column(String, default="created")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)
