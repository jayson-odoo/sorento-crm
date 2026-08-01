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

    # Project sales admin's filing reference, e.g. PS26-0143 (D24). Searchable, and
    # deliberately NOT an identity: it is neither the project code nor a purchase
    # document, it is the string written on every piece of paper for this job.
    admin_ref = Column(String(64), nullable=True, index=True)

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

    # Ladder state (AC-H6). Derived from the clock above and the rung's threshold, but
    # PERSISTED so the daily sweep can notify once per rung instead of every morning.
    # 0 = fine, 1 = owner nudged, 2 = owner warned and management copied, 3 = Unattended.
    stale_level = Column(Integer, nullable=False, server_default="0", default=0)
    # When the project ENTERED the ladder, not when it last moved up it: "untouched since
    # 3 March" is the sentence a manager can act on.
    stale_since = Column(DateTime(timezone=False), nullable=True)
    stale_reason = Column(String(16), nullable=True)  # overdue_task | no_activity

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

    # --- who told us (D6) -------------------------------------------------------------
    # An informant is a data source, never a debtor: BCI, a consultant, an architect who
    # mentioned the job. None of this is ever written to `customers`, and none of it
    # implies the informant will buy anything.
    informant_source = Column(String(32), nullable=True)  # bci | referral | walk_in | ...
    informant_ref = Column(String(180), nullable=True)  # their reference, e.g. a BCI job id
    informant_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True
    )
    # A lone informant with no firm on record is normal, so the name stands on its own.
    informant_contact_name = Column(String(180), nullable=True)

    # --- the acceptance handshake (D7) ------------------------------------------------
    # Assignment is not ownership. A lead sits `assigned` until the salesperson accepts
    # it, which is what makes silence measurable and escalation fair.
    acceptance_state = Column(String(24), nullable=True)  # assigned | accepted | declined
    assigned_at = Column(DateTime(timezone=False), nullable=True)
    accepted_at = Column(DateTime(timezone=False), nullable=True)
    declined_reason = Column(Text, nullable=True)
    declined_at = Column(DateTime(timezone=False), nullable=True)

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


# ------------------------------------------------------------ S3 quotations

# A quotation's commercial result. Distinct from the PROJECT's outcome, which is
# DERIVED from these (AC-E10): won if any quotation is won, lost only when all are.
QUOTATION_OUTCOME_OPEN = "open"
QUOTATION_OUTCOME_WON = "won"
QUOTATION_OUTCOME_LOST = "lost"

# The loss-reason lookup set (AC-E9). Client-editable without a deploy, same mechanism
# as the lead disqualification reasons.
QUOTATION_LOSS_REASON_SET_KEY = "project_quotation_loss_reason"

# What a line is priced per. Sorento quotes a development by repeating unit, not by
# one flat bill of quantities: 300 house units at one basin each is a different
# conversation from 300 basins.
UNIT_TYPE_HOUSE_UNIT = "house_unit"
UNIT_TYPE_BATHROOM = "bathroom"
UNIT_TYPE_FACILITY = "facility"
UNIT_TYPE_COMMON_AREA = "common_area"
UNIT_TYPES = (
    UNIT_TYPE_HOUSE_UNIT,
    UNIT_TYPE_BATHROOM,
    UNIT_TYPE_FACILITY,
    UNIT_TYPE_COMMON_AREA,
)

# How a floor is expressed. Both are needed: category policy is usually "no more than
# 20% off list", but a specific SKU is often "never below RM 950".
FLOOR_MODE_PERCENT = "percent"
FLOOR_MODE_ABSOLUTE = "absolute"
FLOOR_MODES = (FLOOR_MODE_PERCENT, FLOOR_MODE_ABSOLUTE)


class ProjectSeries(Base, CompanyScopedMixin):
    """The catalogue a project is allowed to quote from (AC-E5).

    Nominating a PARENT category covers all its descendants, so a series is a short
    list of groups rather than a hand-maintained list of every SKU -- which is the
    version that goes stale the week after it is written.
    """

    __tablename__ = "project_series"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(150), nullable=False)
    brand_id = Column(
        UUID(as_uuid=False), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_project_series_company_name"),
    )


class ProjectSeriesCategory(Base):
    """One nominated category. Keyed by (series, category) so nominating twice is a
    no-op rather than a duplicate row."""

    __tablename__ = "project_series_categories"

    series_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_series.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_categories.id", ondelete="CASCADE"),
        primary_key=True,
    )


class PriceFloorRule(Base, CompanyScopedMixin):
    """The lowest price a line may carry, per level (AC-E6).

    The LEVEL is implied by which key is set, never stored: product_id set = product
    level, category_id set = category level, both null = system. A stored level column
    would be a second source of truth for something the keys already say, and the two
    would eventually disagree.

    Percent is of the product's LIST price. Absolute is a hard number and ignores list
    entirely, deliberately: "never below RM 950" means it even on a discounted item.

    Audited: a breach report is only arguable if who moved the policy, and when, is
    recoverable. ``created_by`` alone answers that for the first write and no other.
    """

    __tablename__ = "price_floor_rules"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=True
    )
    category_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_categories.id", ondelete="CASCADE"),
        nullable=True,
    )
    mode = Column(String(16), nullable=False, server_default=FLOOR_MODE_PERCENT)
    value = Column(Numeric(12, 2), nullable=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # One rule per level per target. NULLS NOT DISTINCT so the SYSTEM rule (both
        # keys null) is a singleton per company rather than something an admin can
        # accidentally create three of.
        Index(
            "uq_price_floor_rules_company_target",
            "company_id",
            "product_id",
            "category_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )


class ProjectQuotation(Base, CompanyScopedMixin):
    """One priced scope of a project (AC-E1).

    A development is quoted in scopes -- house units, common area, showroom -- and each
    is won or lost on its own. That is why outcome lives here and the project's outcome
    is derived (AC-E10): a project with a won house-unit scope and an open common-area
    scope is still live.
    """

    __tablename__ = "project_quotations"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scope_label = Column(String(150), nullable=False)
    series_id = Column(
        UUID(as_uuid=False), ForeignKey("project_series.id", ondelete="SET NULL"), nullable=True
    )
    notes = Column(Text, nullable=True)

    outcome = Column(
        String(16),
        nullable=False,
        server_default=QUOTATION_OUTCOME_OPEN,
        default=QUOTATION_OUTCOME_OPEN,
    )
    loss_reason = Column(String(150), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_quotations_project", "project_id"),
        Index("ix_project_quotations_outcome", "company_id", "outcome"),
    )


class ProjectQuotationVersion(Base, CompanyScopedMixin):
    """A revision of a quotation (AC-E3, AC-E3a).

    **No ``current_version_id`` and no ``is_frozen`` flag.** Current is
    ``MAX(version_no)`` per quotation and everything below it is frozen. Two facts that
    must agree is one fact too many: the flag and the pointer drift the first time a
    write half-fails, and then nobody can say which version the customer holds.
    """

    __tablename__ = "project_quotation_versions"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = Column(Integer, nullable=False)
    # Stamped when a NEXT version is opened. Kept as a timestamp rather than a boolean
    # because "when was this superseded" is the question people actually ask.
    frozen_at = Column(DateTime(timezone=False), nullable=True)
    issued_by = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    issued_on = Column(Date, nullable=True)
    total_amount = Column(Numeric(15, 2), nullable=False, server_default="0", default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "quotation_id", "version_no", name="uq_project_quotation_versions_no"
        ),
    )


class ProjectQuotationLine(Base, CompanyScopedMixin):
    """One priced item on a version (AC-E4).

    Everything about the product is SNAPSHOTTED at quote time. A catalogue price change
    next month must not rewrite what the customer was quoted, and a discontinued SKU
    must still print on last year's quotation.

    Audited, not just the version above it (AC-E2): the line is where the money changes,
    and an edit that happens not to move the version total -- a quantity swap, a
    description fix -- would otherwise leave no trail at all.
    """

    __tablename__ = "project_quotation_lines"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_quotation_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable: an off-catalog line is legitimate (a bespoke item, or something not yet
    # in the catalogue) and always raises the non-standard alert (AC-E5).
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_code_snapshot = Column(String(100), nullable=True)
    description_snapshot = Column(Text, nullable=True)
    list_price_snapshot = Column(Numeric(12, 2), nullable=True)
    image_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )

    unit_price = Column(Numeric(12, 2), nullable=False, server_default="0", default=0)
    quantity = Column(Numeric(12, 2), nullable=False, server_default="1", default=1)
    uom = Column(String(50), nullable=True)
    unit_type = Column(String(24), nullable=True)
    line_total = Column(Numeric(15, 2), nullable=False, server_default="0", default=0)

    # Alert state, computed on save and STORED (AC-E7): recomputing on read would
    # re-flag old quotations the moment policy changes.
    is_non_standard = Column(Boolean, nullable=False, server_default="false", default=False)
    floor_value_applied = Column(Numeric(12, 2), nullable=True)
    floor_level_applied = Column(String(24), nullable=True)
    is_below_floor = Column(Boolean, nullable=False, server_default="false", default=False)

    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_quotation_lines_version", "version_id", "sort_order"),
        Index("ix_project_quotation_lines_flags", "version_id", "is_below_floor"),
    )


# --------------------------------------------------------------------- S4 samples

# Where the PO came from (AC-F8). The contractor may buy direct, or through a trading
# house that never appears in the quotation -- which is why the source is recorded
# separately from the issuing party rather than inferred from it.
PO_SOURCE_CONTRACTOR_DIRECT = "contractor_direct"
PO_SOURCE_TRADING_HOUSE = "trading_house"
PO_SOURCES = (PO_SOURCE_CONTRACTOR_DIRECT, PO_SOURCE_TRADING_HOUSE)


class ProjectSample(Base, CompanyScopedMixin):
    """A physical sample sent to the developer, bound to a quotation VERSION (AC-F1).

    Binding to the version rather than the quotation is the whole point: "which price
    was the developer looking at when they approved this finish" is only answerable if
    the version is recorded. A new sample cannot be recorded against a SUPERSEDED
    version (AC-F2) -- but one recorded before a revise stays, and stays editable,
    because the developer's feedback normally arrives after the revise and it is the one
    thing the sample exists to capture.
    """

    __tablename__ = "project_samples"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    quotation_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_quotation_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_on = Column(Date, nullable=True)
    submitted_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    developer_feedback = Column(Text, nullable=True)
    salesperson_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_samples_project", "project_id"),
        Index("ix_project_samples_version", "quotation_version_id"),
    )


class ProjectPurchaseOrder(Base, CompanyScopedMixin):
    """A customer PO against a project (AC-F8).

    Its own table, NEVER ``purchase_orders`` (ADR-0002): that table is supplier-side
    procurement, and merging an inbound customer commitment into it would mean every
    procurement report silently counts revenue as spend.

    Bound to a quotation VERSION, because the version is the price the contractor was
    actually last shown, and that is the only fair thing to compare a PO against
    (AC-F9). Unlike a sample, a PO MAY be recorded against a superseded version: the
    contractor buys off the document they were given, which is frequently not the newest
    one, and refusing it would make the PO unrecordable through no fault of the person
    recording it.
    """

    __tablename__ = "project_purchase_orders"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    quotation_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_quotation_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    po_source = Column(String(24), nullable=False, server_default=PO_SOURCE_CONTRACTOR_DIRECT)
    # Who issued it. Separate from po_source deliberately: a trading house PO still names
    # the trading house here, and a contractor-direct PO names the contractor.
    issuing_party_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_parties.id", ondelete="SET NULL"),
        nullable=True,
    )
    po_number = Column(String(100), nullable=False)
    po_date = Column(Date, nullable=True)
    po_amount = Column(Numeric(15, 2), nullable=True)
    notes = Column(Text, nullable=True)

    # --- phase 2: the same PO row, now able to arrive as a scanned document -----------
    # Versioned documents, extracted lines and handwriting cards hang off this row
    # (``app.models.project_so``). A PO keyed in by hand and a PO uploaded as a scan are
    # deliberately ONE row with one number: two tables would mean two answers to "what
    # did the customer commit to".
    #
    # Fields printed on the customer's document, kept as printed.
    term_days = Column(Integer, nullable=True)
    sales_person = Column(String(120), nullable=True)
    customer_order_ref = Column(String(180), nullable=True)
    # Project sales admin's filing reference, e.g. PS26-0143 (D24). Not a project code and
    # not a purchase document: it is how they find the file.
    admin_ref = Column(String(64), nullable=True)

    status = Column(String(24), nullable=False, server_default="draft")
    # A pencil note can name a successor PO months before that document is uploaded, so
    # the pointer stays text until it resolves to a row.
    supersedes_po_number = Column(String(120), nullable=True)
    superseded_by_po_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    approved_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=False), nullable=True)
    countersigned_by = Column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    countersigned_at = Column(DateTime(timezone=False), nullable=True)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_purchase_orders_project", "project_id"),
        Index("ix_project_purchase_orders_version", "quotation_version_id"),
        Index("ix_project_purchase_orders_status", "status"),
        # PO numbers are the issuer's, so they are unique per issuer at best. Scoped to
        # the project instead: recording the same PO number twice on one project is the
        # actual mistake worth stopping.
        UniqueConstraint("project_id", "po_number", name="uq_project_purchase_orders_number"),
    )


class ProjectPurchaseOrderLine(Base, CompanyScopedMixin):
    """One line of a customer PO, with its two mismatch flags (AC-F9).

    The flags are FLAGS, not refusals: a PO that arrived is a fact, and a system that
    declines to record it because a model code differs just means it gets tracked in
    somebody's spreadsheet instead.

    ``quoted_unit_price`` is a snapshot of what the bound version said at the moment the
    PO was checked, for the same reason the price floor is snapshotted (AC-E7): editing
    the quotation next week must not make last week's PO change its mind about whether
    it matched.
    """

    __tablename__ = "project_purchase_order_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    po_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    # What the PO itself called the item. Often the contractor's own code, which is
    # exactly why a mismatch is worth showing rather than resolving.
    product_code = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=False, server_default="0", default=0)
    quantity = Column(Numeric(12, 2), nullable=False, server_default="1", default=1)
    uom = Column(String(50), nullable=True)
    line_total = Column(Numeric(15, 2), nullable=False, server_default="0", default=0)

    quoted_unit_price = Column(Numeric(12, 2), nullable=True)
    model_mismatch = Column(Boolean, nullable=False, server_default="false", default=False)
    price_mismatch = Column(Boolean, nullable=False, server_default="false", default=False)

    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_project_po_lines_po", "po_id", "sort_order"),)
