"""Generic entity-to-attachment link model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class EntityAttachmentLink(Base):
    """Generic link table for attaching resources to any entity type."""
    __tablename__ = "entity_attachment_links"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)

    attachment = relationship("Attachment", foreign_keys=[attachment_id])

    __table_args__ = (
        Index("ix_entity_attachment_links_entity", "entity_type", "entity_id"),
        Index("ix_entity_attachment_links_attachment_id", "attachment_id"),
        Index("uq_entity_attachment_links_unique", "entity_type", "entity_id", "attachment_id", unique=True),
    )

