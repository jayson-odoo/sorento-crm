"""Project Sales module models (ADR-0003, ADR-0004).

Two layers, shipped together and deliberately not separated:

- **Generic skeleton**, mirroring ``dreamz_ems`` so the two products converge:
  ``project_types``, ``project_templates`` (+ roles), ``projects``,
  ``project_parties``, ``project_stakeholders``.
- **Sorento sales extension**, explicitly named and making no pretence of
  generality: ``project_sales_profile``, ``project_brands``.

ADR-0003 exists because the previous attempt (``commercial_core``, commit
c77560009, deleted unused in 7f0eb94f1) was a generic skeleton with nothing fitted
to how Sorento sells. The specific guts are what earn the skeleton.

**Why ``developer_party_id`` and ``normalised_title`` sit on ``projects`` and not on
the sales-profile extension**: the registration lock is
``UNIQUE (company_id, developer_party_id, normalised_title)``, and Postgres cannot
constrain across two tables. The plan originally put those columns on the profile,
which made the constraint unbuildable. Slight dent in generic purity (an EMS event
would leave ``developer_party_id`` null); a real constraint instead of an imaginary
one.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


# A project's commercial result. Distinct from its STATUS, which is a funnel
# position: the terminal status rung is "PO Received", not "Won", because a project
# can receive a PO for one scope while another scope is still being quoted. Every
# metric reads outcome; nothing reads status.
OUTCOME_OPEN = "open"
OUTCOME_WON = "won"
OUTCOME_LOST = "lost"
OUTCOME_DORMANT = "dormant"

# Only an OPEN project blocks a new registration. A lost or dormant match is shown
# as context ("previously pursued by Ali, lost on price") but must not block a
# re-tender three years later.
BLOCKING_OUTCOMES = (OUTCOME_OPEN,)

PARTY_DEVELOPER = "developer"
PARTY_ARCHITECT = "architect"
PARTY_MAIN_CONTRACTOR = "main_contractor"
PARTY_TRADING_HOUSE = "trading_house"
PARTY_CONSULTANT = "consultant"


class ProjectParty(Base, CompanyScopedMixin):
    """An organisation, reusable across projects.

    Reuse is the whole point: it is what makes "which architects should we
    prioritise visiting" answerable. Retyped per project, "Veritas Architects" /
    "Veritas Architect Sdn Bhd" / "veritas" become three rows and the intelligence
    is dead.

    ``customer_id`` is the bridge to the buying ledger, set only once a party
    actually issues a purchase order. Architects never buy, which is exactly why
    they must not live in ``customers``.
    """

    __tablename__ = "project_parties"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    party_type = Column(String(32), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    registration_no = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(150), nullable=True)
    notes = Column(Text, nullable=True)
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_parties_company_type", "company_id", "party_type"),
        Index("ix_project_parties_name", "name"),
    )


class ProjectType(Base, CompanyScopedMixin):
    """A configurable category of project.

    Not every project is a property development: roughly half the project names
    already in the system are hotels, fitouts and renovations, which have no launch
    date to derive a delivery year from.
    """

    __tablename__ = "project_types"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(120), nullable=False)
    code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    # Property developments infer delivery from launch_date + a configurable lag.
    # Every other type must state an explicit delivery window instead.
    derives_delivery_from_launch = Column(
        Boolean, nullable=False, server_default="false", default=False
    )
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_project_types_company_code"),)


class ProjectTemplate(Base, CompanyScopedMixin):
    """A reusable preset belonging to a type.

    Owns the configurable defaults: the stakeholder roles available, and optionally
    its own forked status graph. Same concept as ``dreamz_ems``'s
    ``project_templates``, where an Event is simply a Project of another type.
    """

    __tablename__ = "project_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    type_id = Column(
        UUID(as_uuid=False), ForeignKey("project_types.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "type_id", "name", name="uq_project_templates_name"),
    )


class ProjectTemplateRole(Base, CompanyScopedMixin):
    """A stakeholder role this template offers.

    Roles are template configuration, not an enum, following EMS's
    ``project_template_roles``. Seeded: Decision Maker, Influencer, Info Provider,
    Architect.
    """

    __tablename__ = "project_template_roles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    template_id = Column(
        UUID(as_uuid=False), ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(120), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("template_id", "name", name="uq_project_template_roles_name"),
    )


class Project(Base, CompanyScopedMixin):
    """A pursuit of a single property development by one company.

    Not a delivery container: nothing is built or scheduled against it. It exists
    from the moment a salesperson claims the development, long before money moves.

    Company-scoped, so the same physical development pursued by SRT and by MOCHA is
    two projects and the registration lock applies per company.
    """

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_code = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    # Comparison key for the registration lock. Minimal normalisation (casefold +
    # whitespace collapse) so "Phase 3A" and "Phase 3B" stay distinct.
    normalised_title = Column(Text, nullable=False)

    developer_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="RESTRICT"), nullable=True
    )
    type_id = Column(
        UUID(as_uuid=False), ForeignKey("project_types.id", ondelete="RESTRICT"), nullable=True
    )
    template_id = Column(
        UUID(as_uuid=False), ForeignKey("project_templates.id", ondelete="RESTRICT"), nullable=True
    )

    # Funnel position, on the status engine (entity #1). Nullable so a row can be
    # created before its graph is configured; the service assigns the initial status.
    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id", ondelete="SET NULL"), nullable=True
    )
    # Commercial result, DERIVED from quotation outcomes once quotations exist (S3).
    outcome = Column(String(16), nullable=False, server_default=OUTCOME_OPEN, default=OUTCOME_OPEN)
    loss_reason = Column(String(64), nullable=True)

    owner_user_id = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # The PDF's "Final Negotiation": a FLAG, not a funnel rung, so a re-quote during
    # negotiation does not drag the card backwards and corrupt stage durations.
    is_critical = Column(Boolean, nullable=False, server_default="false", default=False)
    critical_at = Column(DateTime(timezone=False), nullable=True)
    management_support = Column(Text, nullable=True)
    management_notes = Column(Text, nullable=True)

    # Advanced only by REAL work (a human post, or a whitelisted system event), never
    # by opening the record or fixing a typo, so the staleness ladder cannot be gamed.
    last_meaningful_activity_at = Column(DateTime(timezone=False), nullable=True)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # THE registration lock (ADR-0004). Buildable only because both keys live on
        # this table. NULLS NOT DISTINCT so a null developer cannot be used to slip
        # duplicates past it.
        Index(
            "uq_projects_company_developer_title",
            "company_id",
            "developer_party_id",
            "normalised_title",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        UniqueConstraint("company_id", "project_code", name="uq_projects_company_code"),
        Index("ix_projects_company_outcome", "company_id", "outcome"),
        Index("ix_projects_status", "status_id"),
    )


class ProjectSalesProfile(Base):
    """The Sorento-specific half of a project.

    Separate table, not extra columns on ``projects``, so the generic skeleton stays
    portable to EMS. One row per project.
    """

    __tablename__ = "project_sales_profile"

    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    # The legal entity for THIS development, typically a project-specific SPV and
    # usually unknown at registration. Free text: it is an identity, not a buyer.
    registered_company_name = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    architect_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True
    )
    main_contractor_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True
    )
    estimated_sales_value = Column(Numeric(15, 2), nullable=True)
    launch_date = Column(Date, nullable=True)
    # An explicit window overrides the launch_date + lag derivation wherever set.
    expected_delivery_from = Column(Date, nullable=True)
    expected_delivery_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProjectBrand(Base):
    """Brands being pushed into a project. M2M onto the existing ``brands`` table.

    Reuses core brand reference data rather than a project-only list, so a quoted
    product can be checked against the brand it was registered under. Note that
    Mocha is both a brand carried by SRT and a separate company; the two are
    unrelated uses of the name.
    """

    __tablename__ = "project_brands"

    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    brand_id = Column(
        UUID(as_uuid=False), ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class ProjectStakeholder(Base, CompanyScopedMixin):
    """A person on ONE project, with the role they play on THAT project.

    The same QS is a decision maker on one tender and an influencer on the next, so
    the role belongs to the pairing, never to the person. There is no global person
    master: people are typed per project, as in ecohub's ``ProjectContact``.
    ``party_id`` (their firm) is optional, so a lone informant with no firm records.
    """

    __tablename__ = "project_stakeholders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True
    )
    role_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_template_roles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    person_name = Column(String(255), nullable=False)
    job_title = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(150), nullable=True)
    influence = Column(String(16), nullable=True)  # high | medium | low
    is_primary = Column(Boolean, nullable=False, server_default="false", default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_project_stakeholders_project", "project_id"),)


class ProjectCollaborator(Base):
    """A non-owner granted edit rights, via an approved request-to-join."""

    __tablename__ = "project_collaborators"

    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        String(100), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by = Column(String(100), nullable=True)
    granted_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class ProjectTakeoverRequest(Base):
    """The recourse path from a blocked registration (ADR-0004).

    Hard blocking with no way out produces defensive land-grabbing and pushes the
    conflict back into WhatsApp, which is the pain being solved. ``kind='join'`` asks
    for collaborator rights; ``kind='dispute'`` asks a manager for the project.
    """

    __tablename__ = "project_takeover_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requester_user_id = Column(
        String(100), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind = Column(String(16), nullable=False)  # join | dispute
    reason = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, server_default="pending", default="pending")
    decided_by = Column(String(100), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)
    decision_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_takeover_requests_project", "project_id", "status"),
    )
