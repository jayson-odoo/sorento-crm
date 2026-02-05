"""Generic import logging model."""
import uuid
from sqlalchemy import Column, String, DateTime, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base


class ImportLog(Base):
    __tablename__ = "import_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_session_id = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_table = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=True)
    import_type = Column(String(50), nullable=False)
    total_rows = Column(Integer, default=0, nullable=False)
    successful_rows = Column(Integer, default=0, nullable=False)
    created_rows = Column(Integer, default=0, nullable=False)
    updated_rows = Column(Integer, default=0, nullable=False)
    failed_rows = Column(Integer, default=0, nullable=False)
    skipped_rows = Column(Integer, default=0, nullable=False)
    warnings = Column(JSONB, nullable=True)
    errors = Column(JSONB, nullable=True)
    summary = Column(JSONB, nullable=True)
    imported_by = Column(String, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_import_logs_entity_type", "entity_type"),
        Index("ix_import_logs_entity_table", "entity_table"),
        Index("ix_import_logs_import_session_id", "import_session_id"),
        Index("ix_import_logs_imported_by", "imported_by"),
        Index("ix_import_logs_imported_at", "imported_at"),
    )
