"""Audit log model for system-wide change tracking."""
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid


class AuditLog(Base):
    """Records INSERT/UPDATE/DELETE on audited entities with old/new values and actor."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(100), nullable=False, index=True)
    # Polymorphic: holds whatever the audited entity's PK is, which is NOT always a
    # UUID (e.g. MarketSegment's PK is a `code` like 'MSEG-A'). Must stay text —
    # production currently types this column `uuid`, which silently rejects those
    # rows, so market-segment changes have never been audited. See migration 297.
    entity_id = Column(String(100), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # INSERT | UPDATE | DELETE
    user_id = Column(UUID(as_uuid=False), nullable=True)  # system, or user id when available
    # Acting contact (respond_contacts.id) for portal/public-link writes where there is
    # no staff user_id. NULL for staff writes and the `system` automation principal.
    # Display resolves this to the contact name BEFORE the user_id -> staff / "System" fallback.
    contact_id = Column(String(100), nullable=True, index=True)
    changed_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)
    ip_address = Column(String(100), nullable=True)
    # Per-request correlation id (Sub-plan D Tier-2): all rows written during one
    # HTTP request share this, so a multi-row change is traceable as one action.
    trace_id = Column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_changed_at", "changed_at"),
        Index("ix_audit_logs_user_id", "user_id"),
    )
