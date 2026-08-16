"""Chatbot media models: the gate, the ledger and the queued extraction job.

See `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` section 2.

Three tables, deliberately separate:

* ``contact_media_limit`` is the gate plus the per-contact overrides. **Absence of
  a row means denied.** That is how "off for every existing contact" is satisfied
  without a backfill writing a row per contact, and it is fail-closed by
  construction rather than by a default value someone can flip globally. There is
  no system-wide "allow everyone" switch on purpose.
* ``contact_media_usage`` is the metered fact - one append-mostly row per media
  item, refusals included, so "the gate denied everybody" is observable rather
  than invisible. It must not churn, which is why the mutable work state lives
  elsewhere.
* ``media_extraction_job`` is that mutable work state: attempts, result, callback
  delivery. 1:1 with an accepted ledger row, cascading off it.

Timestamps are naive UTC (``DateTime(timezone=False)``) to match every other
table in this repo. The *period* is a separate concept computed in
Asia/Kuala_Lumpur by ``media_access_service`` and stored as ``period_key``, so
nothing downstream has to know which timezone a raw timestamp is in.
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base

# Modalities the endpoint understands, in the order the operator card renders
# them. A plain tuple rather than a DB enum: adding one must not need a migration
# on three tables.
MEDIA_MODALITIES = ("image", "voice")

# The `outcome` vocabulary is: accepted, failed, not_queued, refused_gate,
# refused_burst, refused_quota, refused_duration. Only the first two consume
# monthly quota - a contact refused fifty times still shows their full
# allowance, and neither does one whose item never reached the worker.
QUOTA_CONSUMING_OUTCOMES = ("accepted", "failed")


class ContactMediaLimit(Base):
    """Per-contact, per-modality gate and limit overrides.

    One row per ``(contact_id, modality)``, enforced by a unique constraint rather
    than by making that pair the primary key: the repo's data-model principle is
    that every domain table carries a uuid ``id`` (see
    ``tests/test_schema_uuid_id_principle.py`` for why - the polymorphic key
    columns can only stay uuid-typed if every id they might hold is one). The plan
    wrote the pair as the PK; the uniqueness it was buying is unchanged.

    A NULL ``monthly_limit`` / ``max_clip_seconds`` means inherit the system
    default - the same inherit-unless-overridden shape ``AgentFieldAccess`` uses.
    """

    __tablename__ = "contact_media_limit"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    modality = Column(String(16), nullable=False)

    # The gate. Default false so a row created for any other reason still denies.
    is_allowed = Column(Boolean, nullable=False, default=False, server_default="false")
    monthly_limit = Column(Integer, nullable=True)  # NULL = inherit
    max_clip_seconds = Column(Integer, nullable=True)  # NULL = inherit; voice only
    languages = Column(ARRAY(Text), nullable=True)  # NULL = inherit; voice only

    # Notice bookkeeping: the period each one-per-period customer notice last
    # fired in, stamped in the same transaction as the decision so a notice
    # cannot fire twice for one period even under a retry.
    warned_period = Column(String(7), nullable=True)
    degraded_notified_period = Column(String(7), nullable=True)

    # Plain text, NOT a users FK: the writer may be an integration principal that
    # is not a `users` row, and a gate change must never fail on attribution.
    updated_by = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "contact_id", "modality", name="uq_contact_media_limit_contact_modality"
        ),
        Index("ix_contact_media_limit_contact_id", "contact_id"),
    )


class ContactMediaUsage(Base):
    """One row per media item, including every refusal. The metered fact."""

    __tablename__ = "contact_media_usage"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # What n8n knows. Enforcement reads this, so it is not nullable even when the
    # contact cannot be resolved (an unknown contact is still a recorded refusal).
    respond_io_id = Column(Text, nullable=False)
    contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    modality = Column(String(16), nullable=False)

    # The idempotency key, with `media_ordinal` defaulting to 0. If one respond.io
    # messageId turns out to carry several images, n8n sends an ordinal and no
    # migration is needed; if it does not, the column stays 0 and the key behaves
    # exactly as `(respond_io_id, message_id, modality)`.
    message_id = Column(Text, nullable=False)
    media_ordinal = Column(Integer, nullable=False, default=0, server_default="0")

    period_key = Column(String(7), nullable=False)  # YYYY-MM, Asia/Kuala_Lumpur
    outcome = Column(String(32), nullable=False)
    tier = Column(String(16), nullable=True)  # standard | degraded
    turn_id = Column(Text, nullable=True)  # n8n $execution.id

    bytes = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)  # voice

    # The customer-facing notices this decision produced, stored so a replay and
    # a callback carry the same text the original response did. Without it an
    # n8n retry of a refusal reaches the dealer with no message at all, and
    # `build_callback_body` can only ever hand back an empty list.
    notices = Column(JSONB, nullable=True)

    # Stamped after extraction, for cost attribution.
    model = Column(Text, nullable=True)
    provider = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "respond_io_id",
            "message_id",
            "modality",
            "media_ordinal",
            name="uq_contact_media_usage_idempotency",
        ),
        # The hot enforcement query: count this contact's consumption this period.
        Index(
            "ix_contact_media_usage_enforcement",
            "respond_io_id",
            "modality",
            "period_key",
        ),
        Index("ix_contact_media_usage_contact_created", "contact_id", "created_at"),
    )


class MediaExtractionJob(Base):
    """The queued extraction, 1:1 with an accepted ledger row."""

    __tablename__ = "media_extraction_job"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    usage_id = Column(
        UUID(as_uuid=False),
        ForeignKey("contact_media_usage.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    status = Column(
        String(16), nullable=False, default="queued", server_default="queued"
    )  # queued | running | completed | failed
    modality = Column(String(16), nullable=False)
    tier = Column(String(16), nullable=True)

    media_url = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)

    # Opaque to the CRM by design: the far end may point this at a Wait-node
    # resume URL, a plain webhook, or nothing at all. See PLAN section 1.3.
    callback_url = Column(Text, nullable=True)
    callback_headers = Column(JSONB, nullable=True)
    callback_status = Column(String(16), nullable=True)  # pending | delivered | failed
    callback_attempts = Column(Integer, nullable=False, default=0, server_default="0")

    # Echoed back verbatim so the far end can rebuild the turn without re-reading.
    context = Column(JSONB, nullable=True)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    rq_job_id = Column(Text, nullable=True)  # mirrors the ImportJob.job_id convention

    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    started_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_media_extraction_job_status", "status"),
        Index("ix_media_extraction_job_usage_id", "usage_id"),
    )
