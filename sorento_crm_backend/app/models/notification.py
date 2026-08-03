"""Notification models for in-app, email, and push delivery."""
from sqlalchemy import Column, String, Boolean, CheckConstraint, DateTime, Text, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Notification(Base):
    """One notification, addressed to EITHER a staff user OR a Respond.io contact.

    S4 (AC-H1/AC-H2) made the recipient two-valued. Before it, ``user_id`` was NOT
    NULL, so "tell the contact" had to be implemented outside this table entirely —
    `workflow_submission_notify` sent and wrote an outbox row with no notification
    behind it. One spine records both kinds now, and the outbox correlates back to
    it.

    Exactly one recipient, enforced by ``notifications_recipient_present``: neither
    set is a row no delivery loop can ever address, and both set is a row that fans
    out to two different people depending on which query reads it first.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True, index=True)
    # TEXT, not uuid: ``respond_contacts.id`` is a TEXT column and Postgres refuses a
    # uuid foreign key onto a text primary key (AC-H1a — the fourth column in this
    # build to hit that trap). CASCADE rather than SET NULL because nulling it would
    # violate the recipient CHECK: a contact's notifications go with the contact.
    respond_contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type = Column(String(80), nullable=False, index=True)  # e.g. import_job_finished, import_job_failed
    title = Column(String(512), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSONB, nullable=True)  # payload for deep link, job_id, etc.
    read_at = Column(DateTime(timezone=False), nullable=True)
    archived_at = Column(DateTime(timezone=False), nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    source_entity_type = Column(String(80), nullable=True, index=True)  # e.g. import_job
    # The entity this notification is ABOUT — a real uuid, or NULL for
    # entity-less notifications (e.g. system-health alerts).
    source_entity_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    # Idempotency scope: one notification per (user, source_entity_type,
    # dedup_key, event_type). For an entity notification this equals the entity
    # id; for a batched/periodic one it is a synthetic key
    # (`alert:integration_spike:<ts>`, `digest:<date>`, `{type}_{batch}`).
    dedup_key = Column(String(255), nullable=True, index=True)
    event_type = Column(String(255), nullable=True, index=True)  # e.g. finished, failed; workflow ids can be long

    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        # Exactly one recipient. XOR rather than OR: both columns set is two
        # recipients in one delivery fan-out, and the worker and the outbox renderer
        # would each pick a different one.
        CheckConstraint(
            "(user_id IS NOT NULL) <> (respond_contact_id IS NOT NULL)",
            name="notifications_recipient_present",
        ),
        # TWO partial unique indexes, replacing the single whole-table
        # ``uq_notification_user_dedup_event`` (AC-H1b). Postgres treats NULLs as
        # distinct in a unique constraint, so the moment ``user_id`` became nullable
        # that constraint stopped deduplicating every contact row — silently. The
        # symptom is a customer receiving the same WhatsApp twice, never an error.
        Index(
            "uq_notifications_user_dedup",
            "user_id", "source_entity_type", "dedup_key", "event_type",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_notifications_contact_dedup",
            "respond_contact_id", "source_entity_type", "dedup_key", "event_type",
            unique=True,
            postgresql_where=text("respond_contact_id IS NOT NULL"),
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


class NotificationSubscription(Base):
    """Coverage subscription: ``subscriber_id`` also receives ``target_user_id``'s
    FUTURE SLA assignment/escalation notifications (labelled "covering for <name>").

    Forward-looking delegation, distinct from takeover (which grabs an existing task).
    One subscriber → many targets; one target → many subscribers. At most one ACTIVE
    row per (subscriber, target) pair.
    """

    __tablename__ = "notification_subscriptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active = Column(Boolean, default=True, nullable=False, server_default=text("true"))
    # Per-coverage mode. True = auto-assign the target's future SLA tasks to the
    # subscriber (redirect assignment/escalation); the subscriber must be the SOLE
    # active coverer. False = notify-only (original behaviour): fan-out coverage
    # notification copies, subscriber takes over manually; multiple notify-only
    # coverers per target are allowed. server_default false → existing rows stay
    # notify-only (backward-compatible).
    redirect_assignments = Column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    expires_at = Column(DateTime(timezone=False), nullable=True)
    # Audit: who created this coverage. NULL / == subscriber_id → self-service. A
    # different user → a HoD assigned it on behalf of the coverer (manage_team).
    # SET NULL on delete so removing the HoD doesn't cascade-drop the coverage.
    created_by_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_notification_subscriptions_subscriber_id", "subscriber_id"),
        Index("ix_notification_subscriptions_target_user_id", "target_user_id"),
        # One active subscription per (subscriber, target). Plain unique index on the
        # pair (sqlite-compatible); the service toggles is_active rather than deleting,
        # and re-subscribes by reactivating the existing row.
        Index(
            "uq_notification_subscriptions_subscriber_target",
            "subscriber_id",
            "target_user_id",
            unique=True,
        ),
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
