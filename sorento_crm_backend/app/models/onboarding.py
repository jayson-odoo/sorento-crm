"""Onboarding intake, review and provisioning.

Three tables behind one journey: somebody outside the CRM is asked for a list of
people, an admin reviews it, and the system creates what each person needs.
See ``documentation/plans/UAC-onboarding-intake.md``.

The design decision worth knowing before reading the columns: **the provisioning
ledger lives on the person row**, not in a separate saga table. Each person has
three independent lanes - a CRM user, a WhatsApp contact, a chat-agent seat -
and each carries its own step, its own error and its own captured artifact id.
That is what makes partial state visible: the review page renders its chips
straight off these columns, so "the user was created but the contact was not"
is a thing somebody can SEE rather than a thing they discover a week later.

Lane steps are ``String``, not a Postgres enum, on purpose: Slices 2 and 3 add
values to two of them (``created_local``/``pushed``, ``awaiting_invite``/
``linked``) and adding a value to a PG enum inside a migration transaction is
the migration that goes wrong.
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

# --- Vocabulary ---------------------------------------------------------------

#: Person-level verdicts. Only `approved` rows are provisioned.
REVIEW_PROPOSED = "proposed"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_ON_HOLD = "on_hold"
REVIEW_STATUSES = (REVIEW_PROPOSED, REVIEW_APPROVED, REVIEW_REJECTED, REVIEW_ON_HOLD)

#: Lane steps every lane shares.
LANE_PENDING = "pending"
LANE_DONE = "done"
LANE_FAILED = "failed"
LANE_SKIPPED = "skipped"


class OnboardingTemplate(Base, CompanyScopedMixin):
    """A named bundle of access, so "copy from somebody similar" stops being tribal memory.

    The requester only ever sees ``name`` and ``description`` - never the role
    ids behind them. That is the privacy boundary of the whole feature: she can
    propose "Salesperson" while knowing nothing about roles, permissions or who
    already has what.

    **No team placement, deliberately.** At most one conversation-SLA tier-1 team
    per user is a hard cross-user invariant; a template that placed people on
    teams would break it in bulk, quietly, on the one action designed to run
    hundreds of times.
    """

    __tablename__ = "onboarding_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    #: Applied by `invite_user` at provisioning time, so what is granted is what
    #: the review screen showed - not a copy frozen when the row was typed.
    role_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    company_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    #: Written now, read by Slice 2's contact lane. Present so the template a
    #: captain curates today does not need re-curating when that lane lands.
    access_agent_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    default_needs_system_account = Column(Boolean, nullable=False, server_default=text("true"))
    default_needs_respond_contact = Column(Boolean, nullable=False, server_default=text("false"))
    default_needs_agent_seat = Column(Boolean, nullable=False, server_default=text("false"))

    #: Which user this template was captured from, kept so "why does this
    #: template grant that" has an answer a year later.
    # `users.id` is a String column, not UUID, so every user-id here is String too.
    captured_from_user_id = Column(String(64), nullable=True)
    created_by_user_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_onboarding_templates_company_active", "company_id", "is_active"),
        # One label per company, declared HERE as well as in the migration so a
        # schema built by `create_all` (which is what the test suite runs on)
        # carries the same guarantee the migrated database does. Without it the
        # duplicate-name 409 is untestable, and an untestable constraint is one
        # that quietly stops holding.
        Index(
            "uq_onboarding_templates_company_name",
            "company_id",
            text("lower(btrim(name))"),
            unique=True,
        ),
    )


class OnboardingRequest(Base, CompanyScopedMixin):
    """One batch of people, one intake link, one review.

    Company-scoped because everything the batch produces is: which companies
    each user is granted, which teams could ever route to them. The company is
    chosen when the request is created and is never a column in the uploaded
    file - a sheet from a client whose domain is not ours would otherwise decide
    it.

    Status rides the core status engine (entity type ``onboarding_request``,
    seeded by migration) rather than a bespoke enum, so a second approve is a
    409 by construction of the graph rather than by an `if` somebody has to
    remember to write.
    """

    __tablename__ = "onboarding_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)

    requester_name = Column(String(150), nullable=False)
    requester_email = Column(String(255), nullable=False)
    requester_phone = Column(String(32), nullable=True)

    #: Crockford base32, 48 chars. Multi-use until submitted, then the same
    #: token serves the read-only status page.
    token = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    revoked_at = Column(DateTime(timezone=False), nullable=True)

    status_id = Column(UUID(as_uuid=False), ForeignKey("statuses.id"), nullable=False)
    #: Denormalised alongside the id and carried in lockstep, so a query can ask
    #: "which requests are waiting on review" without a join.
    status_key = Column(String(64), nullable=False)

    requester_note = Column(Text, nullable=True)
    reviewer_note = Column(Text, nullable=True)

    created_by_user_id = Column(String(64), nullable=True)
    sent_at = Column(DateTime(timezone=False), nullable=True)
    submitted_at = Column(DateTime(timezone=False), nullable=True)
    reviewed_by_user_id = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime(timezone=False), nullable=True)
    provisioned_at = Column(DateTime(timezone=False), nullable=True)

    #: The original upload, retained for tracing exactly as the import jobs do.
    source_file_name = Column(String(255), nullable=True)
    source_storage_provider = Column(String(16), nullable=True)
    source_storage_key = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    people = relationship(
        "OnboardingPerson",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="OnboardingPerson.row_number",
    )

    __table_args__ = (
        Index("ix_onboarding_requests_company_status", "company_id", "status_key"),
    )


class OnboardingPerson(Base, CompanyScopedMixin):
    """One named person, and everything the system has done about them.

    Both a raw and a normalised copy of phone and email are kept. The raw value
    is what the requester typed and is what she is shown back - correcting her
    spelling in the grid she is looking at reads as the system losing her input.
    The normalised value is what collides against ``users.email``,
    ``users.contact_number`` and ``respond_contacts.phone_number``, which is the
    only comparison that means anything (half the sample file's addresses carry
    trailing whitespace).
    """

    __tablename__ = "onboarding_people"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("onboarding_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_number = Column(Integer, nullable=False)

    full_name = Column(String(200), nullable=False)
    nick_name = Column(String(100), nullable=True)
    phone_raw = Column(String(64), nullable=True)
    #: MSISDN-normalised. Null when the raw value could not be read - a warning
    #: on the row, never a rejected file.
    phone = Column(String(32), nullable=True)
    email_raw = Column(String(255), nullable=True)
    #: `lower(btrim())`. Null when no email was supplied.
    email = Column(String(255), nullable=True)

    #: The sheet's own section header ("SALES PERSON"). The only access signal a
    #: phone list carries, and what a section-level template default keys on.
    section_label = Column(String(120), nullable=True)

    template_id = Column(
        UUID(as_uuid=False),
        ForeignKey("onboarding_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    requester_note = Column(Text, nullable=True)
    reviewer_note = Column(Text, nullable=True)

    needs_system_account = Column(Boolean, nullable=False, server_default=text("true"))
    needs_respond_contact = Column(Boolean, nullable=False, server_default=text("false"))
    needs_agent_seat = Column(Boolean, nullable=False, server_default=text("false"))

    review_status = Column(String(20), nullable=False, server_default=text("'proposed'"))
    rejection_reason = Column(Text, nullable=True)

    # --- lane 1: the CRM user (this slice) ---
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_step = Column(String(20), nullable=False, server_default=text("'pending'"))
    user_error = Column(Text, nullable=True)

    # --- lane 2: the WhatsApp contact (Slice 2) ---
    respond_contact_id = Column(UUID(as_uuid=False), nullable=True)
    contact_step = Column(String(20), nullable=False, server_default=text("'pending'"))
    contact_error = Column(Text, nullable=True)

    # --- lane 3: the chat-agent seat (Slice 3) ---
    linked_respond_user_id = Column(String(64), nullable=True)
    agent_step = Column(String(20), nullable=False, server_default=text("'pending'"))
    agent_error = Column(Text, nullable=True)

    invite_marked_sent_at = Column(DateTime(timezone=False), nullable=True)
    provisioned_at = Column(DateTime(timezone=False), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    request = relationship("OnboardingRequest", back_populates="people")

    __table_args__ = (
        UniqueConstraint("request_id", "row_number", name="uq_onboarding_people_request_row"),
        Index("ix_onboarding_people_request_review", "request_id", "review_status"),
        Index("ix_onboarding_people_email", "email"),
        Index("ix_onboarding_people_phone", "phone"),
    )
