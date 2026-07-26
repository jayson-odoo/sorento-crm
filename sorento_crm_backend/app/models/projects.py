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
    # Ownership changes, retitles and stage moves are exactly what people dispute
    # later, so the project itself is audited too.
    __audit_track__ = True

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
    # Where this pursuit came from, when it came from a lead (AC-O10). Nullable
    # because a project may be registered directly -- a tender notice arrives and is
    # claimed the same hour, with no prior sighting. SET NULL rather than CASCADE: a
    # deleted lead must never take a live registration with it.
    lead_id = Column(
        UUID(as_uuid=False), ForeignKey("project_leads.id", ondelete="SET NULL"), nullable=True
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
        Index("ix_projects_lead", "lead_id"),
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


# Task lifecycle axis. Deliberately SEPARATE from ``category``: conflating them was
# the design error the ecohub reference pass caught. Phase is where in the project's
# life the task sits; category is which work-stream it belongs to.
TASK_PHASE_PURSUIT = "pursuit"
TASK_PHASE_DELIVERY = "delivery"
TASK_PHASES = (TASK_PHASE_PURSUIT, TASK_PHASE_DELIVERY)

# Artifacts a task may point at (AC-N5a). Adapted from ecohub's task->invoice link;
# the tables arrive in S3/S4, so the link is stored as a loose (type, id) pair rather
# than a FK that cannot exist yet.
TASK_LINK_QUOTATION_VERSION = "quotation_version"
TASK_LINK_SAMPLE = "sample"
TASK_LINK_PURCHASE_ORDER = "purchase_order"
TASK_LINK_TYPES = (
    TASK_LINK_QUOTATION_VERSION,
    TASK_LINK_SAMPLE,
    TASK_LINK_PURCHASE_ORDER,
)


class ProjectTemplateTask(Base, CompanyScopedMixin):
    """A checklist item a template hands to every project created from it (AC-N1).

    Maps onto ecohub's ``TaskTemplateItem``. Lives on ``project_templates`` because
    that layer already owns the stakeholder roles, so a template owning its task list
    adds no new generic concept.
    """

    __tablename__ = "project_template_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    template_id = Column(
        UUID(as_uuid=False), ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_phase = Column(
        String(16), nullable=False, server_default=TASK_PHASE_PURSUIT, default=TASK_PHASE_PURSUIT
    )
    # Work-stream label (Spec-in, Sampling, Commercial, Logistics). Free-form per
    # template on purpose: every project type streams its work differently.
    category = Column(String(120), nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    # Days after the project is registered that this task is due. Null = no due date,
    # which is honest for "chase the PO" where the date depends on events not elapsed
    # time.
    default_offset_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_template_tasks_template", "template_id", "sort_order"),
    )


class ProjectTask(Base, CompanyScopedMixin):
    """A unit of work on one project, on the status engine as entity #2.

    Not a ticket: a ticket is raised BY someone about a problem and carries SLA
    response/resolution clocks and Respond.io links, whereas a task is work I plan.
    They do not collide.

    This is also what makes a project's next action derivable, which is why
    ``next_action_date`` does not exist anywhere (AC-N6): two records of the same
    promise drift apart.
    """

    __tablename__ = "project_tasks"
    # AC-N7: the per-task history timeline is delivered FROM the audit trail, which
    # already captures per-field diffs with an actor. A dedicated history table would
    # be a second store to keep in sync, and the one nobody writes to is the one the
    # timeline reads.
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    task_phase = Column(
        String(16), nullable=False, server_default=TASK_PHASE_PURSUIT, default=TASK_PHASE_PURSUIT
    )
    category = Column(String(120), nullable=True)

    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id", ondelete="SET NULL"), nullable=True
    )
    assignee_user_id = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Escalate and Stuck cannot be set without their context (AC-N4a), guarded in the
    # service rather than trusted to the dialog: "Escalated" with nobody named, or
    # "Stuck" with no reason, is a status that tells the next reader nothing.
    escalated_to_user_id = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    stuck_reason = Column(Text, nullable=True)

    start_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)

    source_template_task_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_template_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Loose pair, not a FK: quotation versions, samples and POs arrive in later
    # slices, and a FK to a table that does not exist yet cannot be written.
    linked_entity_type = Column(String(32), nullable=True)
    linked_entity_id = Column(UUID(as_uuid=False), nullable=True)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_tasks_project_phase", "project_id", "task_phase"),
        Index("ix_project_tasks_status", "status_id"),
        # "My Tasks" reads open tasks for one user across every project, ordered by
        # due date, so it is worth an index of its own (AC-N9).
        Index("ix_project_tasks_assignee_due", "assignee_user_id", "due_date"),
    )


# A lead's own result axis, deliberately NOT reusing the project outcomes. A lead is
# not won or lost: it is qualified into a project (which then has its own outcome) or
# disqualified. Reusing OUTCOME_WON here would make "won leads" and "won projects"
# double-count the same pursuit in every report.
LEAD_OUTCOME_OPEN = "open"
LEAD_OUTCOME_QUALIFIED = "qualified"
LEAD_OUTCOME_DISQUALIFIED = "disqualified"

# Where the rumour came from. Free-form `source_detail` carries the specifics; this
# is the reportable bucket.
LEAD_SOURCE_SITE_VISIT = "site_visit"
LEAD_SOURCE_ARCHITECT = "architect"
LEAD_SOURCE_CONTRACTOR = "contractor"
LEAD_SOURCE_DEALER = "dealer"
LEAD_SOURCE_INBOUND = "inbound"
LEAD_SOURCE_OTHER = "other"
LEAD_SOURCES = (
    LEAD_SOURCE_SITE_VISIT,
    LEAD_SOURCE_ARCHITECT,
    LEAD_SOURCE_CONTRACTOR,
    LEAD_SOURCE_DEALER,
    LEAD_SOURCE_INBOUND,
    LEAD_SOURCE_OTHER,
)

# The lookup set the disqualification reason must come from (AC-O6). A free-text
# reason cannot be reported on, and "not interested" typed nine different ways is
# what kills a conversion metric.
LEAD_DISQUALIFY_REASON_SET_KEY = "project_lead_disqualify_reason"


class ProjectLead(Base, CompanyScopedMixin):
    """A sighting: somebody heard about a development before it is ours to claim.

    **A lead is NOT exclusive** (AC-O3). No fuzzy lock, no clash block, no unique
    index on the title. Several salespeople may record the same rumour, because
    locking hearsay produces a worse land-grab than locking tenders: the first person
    to type a guess would own a development nobody has confirmed exists, and a lead
    often has no developer to lock on anyway.

    Ownership locks at QUALIFY, which is where the registration clash check finally
    runs (AC-O4). One lead may yield SEVERAL projects: a masterplan sighting turns
    into a separate registration per phase (AC-O5).
    """

    __tablename__ = "project_leads"
    # Qualify, disqualify and reassignment are exactly the decisions people dispute,
    # same reasoning as `projects`.
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    lead_code = Column(String(64), nullable=False)

    # Required (AC-O1), matching ecohub's non-nullable `Lead.clientId`. Somebody told
    # us, so there is always a somebody. RESTRICT rather than SET NULL: silently
    # orphaning the lead would leave a rumour with no source.
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    # Optional: at sighting time the developer is frequently the unknown.
    developer_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="RESTRICT"), nullable=True
    )

    title = Column(Text, nullable=False)
    # Kept for the informational near-duplicate hint on the list (AC-O3). Same
    # normalisation as `projects.normalised_title` so a lead can be compared against
    # registered projects with the one shared helper, NOT to enforce anything.
    normalised_title = Column(Text, nullable=False)

    source = Column(String(32), nullable=True)
    source_detail = Column(Text, nullable=True)
    estimated_value = Column(Numeric(15, 2), nullable=True)
    location = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Status engine entity #3 (AC-O7). Leads have no template, so no scoped graphs:
    # one lead funnel per install.
    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id", ondelete="SET NULL"), nullable=True
    )
    outcome = Column(
        String(16), nullable=False, server_default=LEAD_OUTCOME_OPEN, default=LEAD_OUTCOME_OPEN
    )
    disqualified_reason = Column(String(150), nullable=True)
    qualified_at = Column(DateTime(timezone=False), nullable=True)

    owner_user_id = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # The code is unique; the TITLE deliberately is not. See the class docstring.
        UniqueConstraint("company_id", "lead_code", name="uq_project_leads_company_code"),
        Index("ix_project_leads_company_outcome", "company_id", "outcome"),
        Index("ix_project_leads_customer", "customer_id"),
        Index("ix_project_leads_status", "status_id"),
        # The near-duplicate hint scans normalised titles within a company.
        Index("ix_project_leads_company_normalised", "company_id", "normalised_title"),
    )
