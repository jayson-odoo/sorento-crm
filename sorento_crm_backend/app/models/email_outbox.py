"""Email outbox + per-event configs - single chokepoint for all outbound mail.

Every outbound email is one row in `email_outbox` (status: pending|sending|sent|failed|cancelled|deferred).
A scheduled drainer worker reads pending rows, applies rate-limit guardrails, and dispatches via SMTP.

`email_event_configs` rows are seeded from `app.services.email_event_registry.EMAIL_EVENT_REGISTRY` at
startup. They give operators a per-event kill switch + optional rate override without redeploy.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid


class EmailOutbox(Base):
    """One row = one outgoing email. The drainer is the only producer of SMTP traffic."""
    __tablename__ = "email_outbox"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_key = Column(String(120), nullable=False, index=True)

    recipient_email = Column(String(320), nullable=False, index=True)
    recipients_json = Column(JSONB, nullable=True)

    subject = Column(String(1024), nullable=False)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    from_name = Column(String(255), nullable=True)

    metadata_json = Column(JSONB, nullable=True)

    priority = Column(Integer, nullable=False, default=10)
    status = Column(String(32), nullable=False, default="pending")
    scheduled_for = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    sent_at = Column(DateTime(timezone=False), nullable=True)

    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    error_message = Column(Text, nullable=True)
    cancel_reason = Column(String(120), nullable=True)

    coalesce_key = Column(String(255), nullable=True, index=True)

    # An optional document to attach, held as a storage reference rather than bytes: the row is
    # read on every drain pass and a megabyte of base64 in it would be paid for on each one. The
    # drainer fetches the object at send time. Nullable, so every existing producer is
    # unaffected - `send_mime_email` already accepted attachments, the outbox was the one path
    # that could not pass any, and forking a second SMTP producer to gain that was the
    # alternative.
    attachment_filename = Column(String(255), nullable=True)
    attachment_storage_provider = Column(String(16), nullable=True)
    attachment_storage_key = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_email_outbox_drain", "status", "scheduled_for", "priority"),
        Index("ix_email_outbox_recipient_created", "recipient_email", "created_at"),
        Index("ix_email_outbox_coalesce", "coalesce_key", "status"),
    )


class EmailEventConfig(Base):
    """Per-event kill switch + optional rate overrides. Seeded from registry on startup."""
    __tablename__ = "email_event_configs"

    event_key = Column(String(120), primary_key=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    rate_per_window_override = Column(Integer, nullable=True)
    window_seconds_override = Column(Integer, nullable=True)
    priority_override = Column(Integer, nullable=True)
    coalesce_window_seconds_override = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
