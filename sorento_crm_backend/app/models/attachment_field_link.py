"""Polymorphic per-row, per-field attachment linkage.

One row per (entity_type, entity_id, attachment_id, field_key). Sits orthogonal
to the four existing entity-attachment join tables (``product_attachments``,
``promotion_attachments``, ``inbound_shipments.attachment_id``,
``forms.attachment_id``) - only adds the field-level dimension.

Populated by the link APIs: when n8n (or the FE manual link) creates a per-row
attachment link, ``AttachmentFieldLinkService.apply_template_to_row`` reads
the attachment's ``target_field_keys`` template (or an explicit override) and
inserts the relevant rows here.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class AttachmentFieldLink(Base):
    __tablename__ = "attachment_field_links"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    attachment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_key = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        Index("ix_afl_entity", "entity_type", "entity_id"),
        Index("ix_afl_attachment_id", "attachment_id"),
        Index(
            "uq_afl_unique",
            "entity_type",
            "entity_id",
            "attachment_id",
            "field_key",
            unique=True,
        ),
    )
