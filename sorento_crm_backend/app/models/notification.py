"""Notification models for in-app, email, and push delivery."""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Notification(Base):
    """User notification record (in-app)."""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    type = Column(String(80), nullable=False, index=True)  # e.g. import_job_finished, import_job_failed
    title = Column(String(512), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSONB, nullable=True)  # payload for deep link, job_id, etc.
    read_at = Column(DateTime(timezone=False), nullable=True)
    archived_at = Column(DateTime(timezone=False), nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    # Idempotency: one notification per (user, source, event)
    source_entity_type = Column(String(80), nullable=True, index=True)  # e.g. import_job
    source_entity_id = Column(String(255), nullable=True, index=True)  # e.g. job_id
    event_type = Column(String(80), nullable=True, index=True)  # e.g. finished, failed

    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        UniqueConstraint(
            "user_id", "source_entity_type", "source_entity_id", "event_type",
            name="uq_notification_user_source_event",
        ),
    )


class NotificationDelivery(Base):
    """Per-channel delivery status for a notification."""
    __tablename__ = "notification_deliveries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id = Column(
        UUID(as_uuid=False),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel = Column(String(32), nullable=False, index=True)  # in_app, email, web_push
    status = Column(String(32), nullable=False, default="pending")  # pending, sent, failed
    sent_at = Column(DateTime(timezone=False), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_notification_deliveries_notification_id_channel", "notification_id", "channel"),
    )


class PushSubscription(Base):
    """Web push subscription per user/device for browser notifications."""
    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    endpoint = Column(Text, nullable=False)
    p256dh = Column(Text, nullable=False)  # public key
    auth = Column(Text, nullable=False)  # auth secret
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
