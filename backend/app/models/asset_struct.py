from sqlalchemy import JSON, Column, Float, String

from app.models.base import Base


class AssetLayer(Base):
    """One editable layer extracted by the AssetStruct engine (Phase 13)."""

    __tablename__ = "asset_layers"

    id = Column(String, primary_key=True)
    asset_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    image_url = Column(String)
    mask_url = Column(String)
    bbox = Column(JSON)
    confidence = Column(Float, default=0.0)


class AssetNode(Base):
    """Node of the asset relationship graph (Phase 13)."""

    __tablename__ = "asset_nodes"

    id = Column(String, primary_key=True)
    asset_id = Column(String, nullable=False, index=True)
    parent_id = Column(String, nullable=True)
    type = Column(String, nullable=False)
    metadata_json = Column(JSON, default=dict)
