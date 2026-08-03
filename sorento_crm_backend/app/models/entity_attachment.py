"""Generic entity-to-attachment link model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Integer, Index, Numeric, Text
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

    # --- The AI upload verdict (AC-M22), on the LINK and not on `attachments`.
    # The same file scored against consumer-intake guidance and against collection
    # -proof guidance gets two different numbers, and a column on the file could
    # only ever hold one of them.
    #
    # ai_validation_state answers "may I trust ai_score" and ai_validation_reason
    # answers "why not" (AC-M22a). Without them `ai_score IS NULL` means three
    # things at once - the type does not validate, the model timed out, the row
    # predates the slice - and any UI reading NULL as failure refuses a good photo
    # because the network was slow. `unvalidated` is a DISTINCT state from a low
    # score, never a NULL and never a zero. NULL in both = no claim was made, which
    # is what every pre-slice row and every opted-out type honestly says.
    ai_validation_state = Column(String(20), nullable=True)  # scored | unvalidated
    ai_validation_reason = Column(String(32), nullable=True)  # timeout | error | no_guidance | no_provider | unsupported_media
    # Integer 0-100, the same scale as attachment_types.min_score (AC-M22b).
    ai_score = Column(Integer, nullable=True)
    ai_suggestion = Column(Text, nullable=True)
    # "Used anyway, because ..." (AC-M24). It is itself the metric that says the
    # GUIDANCE is wrong rather than the uploader, which is why the service refuses
    # one on a link that never failed.
    override_reason = Column(Text, nullable=True)
    # Where THIS photo was taken. Numeric(10,7) deliberately matches
    # complaints.latitude / longitude (the Site pin, AC-B21): the two are read side
    # by side, and a capture pin rounded coarser than the Site pin makes "was this
    # photo taken at the site" unanswerable at the precision it is asked. Nullable
    # because denied or unavailable is the ordinary case indoors (AC-M27).
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)

    attachment = relationship("Attachment", foreign_keys=[attachment_id])

    __table_args__ = (
        Index("ix_entity_attachment_links_entity", "entity_type", "entity_id"),
        Index("ix_entity_attachment_links_attachment_id", "attachment_id"),
        Index("uq_entity_attachment_links_unique", "entity_type", "entity_id", "attachment_id", unique=True),
    )

