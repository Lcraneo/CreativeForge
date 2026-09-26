from sqlalchemy import JSON, Column, DateTime, Integer, String

from app.models.base import Base, utcnow


class ModelArtifact(Base):
    """Registered model artifact (Phase 20.15 Model Registry).

    Lifecycle: staged -> production | archived. `weights` holds what the
    serving path loads (e.g. the DNA projection head scale vector).
    """

    __tablename__ = "model_artifacts"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String, default="staged")
    metrics = Column(JSON, default=dict)
    config = Column(JSON, default=dict)
    weights = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TrainingRun(Base):
    """Training pipeline run record (Phase 20.15)."""

    __tablename__ = "training_runs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    status = Column(String, default="completed")
    report = Column(JSON, default=dict)
    artifact_id = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow)
