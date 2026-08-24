"""User submission portal models.

Contact-scoped tokens grant a contact (identified by Respond.io contact id) access
to view and edit their own submissions across complaints, stock inquiries,
purchase requests and sponsorship forms - without a CRM login. After token
expiry the contact re-verifies via OTP sent to their phone via Respond.io.
"""
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class PortalToken(Base):
    __tablename__ = "portal_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(255), unique=True, nullable=False, index=True)
    contact_id = Column(Text, nullable=False)
    space_id = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    revoked_at = Column(DateTime(timezone=False), nullable=True)
    verified_at = Column(DateTime(timezone=False), nullable=True)  # OTP-verified gate; NULL = first visit must verify
    # Admin "view as contact" tokens: excluded from the sliding 30-day TTL and
    # session-scoped on the FE (never written to localStorage).
    is_impersonation = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_portal_tokens_contact_id", "contact_id"),
        Index("ix_portal_tokens_expires_at", "expires_at"),
    )


class PortalOtpCode(Base):
    __tablename__ = "portal_otp_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    contact_id = Column(Text, nullable=False)
    space_id = Column(Text, nullable=False)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    consumed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_portal_otp_codes_contact_id", "contact_id"),
        Index("ix_portal_otp_codes_created_at", "created_at"),
    )


class PortalFormRevision(Base):
    """One row per submitted version of a portal submission (PLAN-portal-submission-revisions).

    Generic on ``(source_entity_type, source_entity_id)`` - the engine knows nothing
    about stock inquiries. Deliberately NOT company-scoped (UAC J5): the parent entity
    already carries the company, and the portal reads these rows under a contact token
    where no company scope applies. Do not add CompanyScopedMixin here or every portal
    read fails closed.
    """

    __tablename__ = "portal_form_revisions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_type = Column(String(50), nullable=False)  # stock_inquiry | purchase_request | sponsorship_form | complaint
    # Polymorphic (no FK). Every portal submission type keys on a uuid id, matching
    # conversation_sla_tracking.source_entity_id.
    source_entity_id = Column(UUID(as_uuid=False), nullable=False)
    # TWO counters, never collapsed into one (UAC C0):
    #   version_no  - every submitted version, for history ordering. Unique per entity.
    #   revision_no - contact-initiated revisions only, the cap counter. NOT unique:
    #                 a resubmission after an office rejection repeats the current value.
    version_no = Column(Integer, nullable=False)
    revision_no = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False)  # original | revision | resubmission
    # NULL only for `original`. For `resubmission` this holds the office rejection
    # the contact is answering. Immutable once written (UAC D2).
    reason = Column(Text, nullable=True)
    # Stage output this revision invalidated, snapshotted before being cleared on the
    # entity (UAC FB2), e.g. the superseded purchasing_response.
    invalidated_json = Column(JSONB, nullable=True)
    snapshot_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    attachments_json = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # The PRIMARY (newest) voided stage. NULL for revision 0 and for a revision that
    # found nothing open. Kept scalar because that is the overwhelmingly common shape
    # and every reader - the office timeline, the portal history - renders it.
    voided_stage_code = Column(String(100), nullable=True)
    # users.id of whoever was working the voided stage. No FK on purpose: this is a
    # historical record and must survive the user being deleted (mirrors
    # stock_inquiries.rejected_by / voided_by).
    voided_assignee_user_id = Column(Text, nullable=True)
    # EVERY stage this revision voided, newest first:
    # ``[{"stage_code": ..., "assignee_user_id": ...}, ...]``.
    #
    # A form can sit with two stages open at once (a purchase request with project
    # sales and approval), and a revision voids all of them and tells all of their
    # handlers. Recording only ``voided_stage_code`` under-reported exactly that: two
    # people were told to stop and history named one. NULL when nothing was open.
    voided_stages_json = Column(JSONB, nullable=True)
    submitted_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)  # naive UTC
    submitted_by_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True
    )
    # Revision 0 reconstructed from current state on first revise for submissions that
    # predate this feature (UAC G2) - labelled "Original (reconstructed)" in the UI.
    is_reconstructed = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_entity_type",
            "source_entity_id",
            "version_no",
            name="uq_portal_form_revisions_entity_version",
        ),
        Index(
            "ix_portal_form_revisions_source_entity",
            "source_entity_type",
            "source_entity_id",
        ),
    )


class PortalRevisionConfig(Base):
    """Per-portal-type revision policy (UAC A2). One row per portal submission type.

    A missing row means disabled - the policy resolver fails closed. All four types are
    seeded so turning one on is a checkbox, never a migration.
    """

    __tablename__ = "portal_revision_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    max_revisions = Column(Integer, nullable=True)  # NULL = inherit system_settings.portal_max_revisions
    allowed_statuses = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # NULL = the first stage of this type's form-SLA chain. Declared once, here: the
    # adapter only maps a stage to the status the entity should carry (UAC J4).
    restart_stage_code = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # Named explicitly so a create_all-built test schema and a migrated schema carry
        # the SAME constraint name - the config seed upserts against it.
        UniqueConstraint("source_entity_type", name="uq_portal_revision_configs_type"),
    )


class PortalRevisionDraft(Base):
    """An in-progress revision, saved by the contact before Send revision.

    Generic on ``(source_entity_type, source_entity_id)``, same as
    :class:`PortalFormRevision`, and deliberately NOT company-scoped for the same
    reason: the parent entity already carries the company, and the portal reads
    this table under a contact token where no company scope applies.
    """

    __tablename__ = "portal_revision_drafts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_type = Column(String(50), nullable=False)
    source_entity_id = Column(UUID(as_uuid=False), nullable=False)
    # The internal respond_contacts.id that owns this draft - what
    # PortalToken.contact_id holds (NOT the Respond.io respond_io_id).
    contact_id = Column(UUID(as_uuid=False), nullable=False)
    # The entity's revision_no when the draft was started; staleness is
    # base_revision_no != entity.revision_no.
    base_revision_no = Column(Integer, nullable=False)
    payload_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # One open draft per submission.
        UniqueConstraint(
            "source_entity_type", "source_entity_id", name="uq_portal_revision_drafts_entity"
        ),
        Index("ix_portal_revision_drafts_contact_id", "contact_id"),
    )
