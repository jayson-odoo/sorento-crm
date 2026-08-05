"""Access control models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Table, Text, Index, Integer, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class ContactAccessType(Base):
    """Configurable catalog for contact access types (e.g. end_user, dealer, sorento_dealer). Used for promotion/attachment visibility and contact classification."""
    __tablename__ = "contact_access_types"

    code = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, nullable=True)
    # Admin-curated synonym list ("customer", "homeowner" → end_user). Consumed by
    # ContactAccessTypeService.enforce_access_levels_for_contact to resolve free-text
    # AI / user phrasing against the canonical code.
    keywords = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_contact_access_types_is_active", "is_active"),
    )


# Many-to-many: a respond contact can have multiple access types. Replaces the
# legacy single-valued respond_contacts.access_type_code FK so promotion /
# attachment visibility can be evaluated as an overlap between the contact's
# assigned codes and the resource's access_levels JSONB array.
respond_contact_access_types = Table(
    "respond_contact_access_types",
    Base.metadata,
    Column(
        "contact_id",
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "access_type_code",
        String(50),
        ForeignKey("contact_access_types.code", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    ),
    Index("ix_respond_contact_access_types_contact_id", "contact_id"),
    Index("ix_respond_contact_access_types_access_type_code", "access_type_code"),
)


class MarketSegment(Base):
    """Configurable catalog of market segments (retail / project) for CS routing.

    A respond contact carries the segment(s) it belongs to; a team membership
    carries the segment(s) that member serves. team-members / next-assignee
    intersect the two to route a conversation to the right customer-service pool.
    Admin-manageable (add / rename / activate / reorder) via Settings.
    """
    __tablename__ = "market_segments"

    # uuid surrogate PK (design principle: every domain table has a uuid `id`).
    # `code` stays the human-facing business key - unique, and the FK target for
    # customers / respond_contact_market_segments / team_member_market_segments.
    id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, nullable=True)
    # SCM (M2): default demand nature for customers in this segment (continuous | spike).
    demand_nature = Column(String(20), nullable=True)
    # When true, contacts in this segment are offered in the "Requested by" /
    # "Salesperson" requestor picker on PR / SF / stock inquiry (portal + CRM).
    # Fail closed: no flagged segment means the picker offers only the submitter
    # and the currently-saved requestor. Admin-visible in Market Segments.
    is_requestor_selectable = Column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_market_segments_is_active", "is_active"),
    )


# Many-to-many: a respond contact belongs to zero+ market segments. Empty = the
# contact matches every member (minimum configuration).
respond_contact_market_segments = Table(
    "respond_contact_market_segments",
    Base.metadata,
    Column(
        "contact_id",
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "segment_code",
        String(50),
        ForeignKey("market_segments.code", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=False), server_default=func.now(), nullable=False),
    Index("ix_respond_contact_market_segments_contact_id", "contact_id"),
    Index("ix_respond_contact_market_segments_segment_code", "segment_code"),
)


# Many-to-many: a team membership serves zero+ market segments. Empty = the
# member serves every contact (untagged member = serves all).
team_member_market_segments = Table(
    "team_member_market_segments",
    Base.metadata,
    Column(
        "team_member_id",
        UUID(as_uuid=False),
        ForeignKey("team_members.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "segment_code",
        String(50),
        ForeignKey("market_segments.code", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=False), server_default=func.now(), nullable=False),
    Index("ix_team_member_market_segments_team_member_id", "team_member_id"),
    Index("ix_team_member_market_segments_segment_code", "segment_code"),
)


class RespondContact(Base):
    __tablename__ = "respond_contacts"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=True)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    respond_io_id = Column(Text, nullable=True)  # Respond.io contact id for inbox URL
    # Stable opaque slug for the bookmarkable portal URL /portal/c/{slug}.
    # Identity hint, not a credential - lazily minted on first portal-link use.
    portal_slug = Column(String(16), nullable=True, unique=True, index=True)
    workspace_id = Column(UUID(as_uuid=False), ForeignKey("respond_workspaces.id", ondelete="SET NULL"), nullable=True)
    # Arbitrary per-contact conversation state. Read/overwritten wholesale by
    # GET|PUT /api/v1/external/conversation-variables/{respond_io_id}.
    session_vars = Column(JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)

    contact_accesses = relationship(
        "ContactAgentAccess",
        back_populates="contact",
        cascade="all, delete-orphan",
    )
    # Many-to-many: contact ↔ access types catalog. Source of truth for which
    # access codes apply to this contact (used by overlap filters on promotion /
    # attachment visibility). Configurable per contact via the FE; no longer
    # synced from Respond.io.
    access_types = relationship(
        "ContactAccessType",
        secondary=respond_contact_access_types,
        order_by="ContactAccessType.sort_order, ContactAccessType.code",
    )
    # Many-to-many: contact ↔ market segments (retail / project). Empty = matches
    # every CS member (minimum config). Configured per contact in the FE.
    market_segments = relationship(
        "MarketSegment",
        secondary=respond_contact_market_segments,
        order_by="MarketSegment.sort_order, MarketSegment.code",
    )
    workspace = relationship("RespondWorkspace", back_populates="respond_contacts")

    __table_args__ = (
        Index("ix_respond_contacts_phone_number", "phone_number"),
        Index("ix_respond_contacts_respond_io_id", "respond_io_id"),
        Index("ix_respond_contacts_workspace_id", "workspace_id"),
    )


class RespondContactCsRouting(Base):
    """Per-salesman → CS PIC pin (pin-point assignment) overriding round-robin.

    When a procurement form-SLA customer-service stage spawns at approval, the
    assignee resolver (`form_sla_service._start_for_config`) looks up an active pin
    for (respond_contact_id, use_case). A valid pin — where ``cs_pic`` is a member of
    the stage's tier-1 CS team and is active — assigns that user directly; any miss
    (no pin / stale pin / inactive user / non-member) falls back to the existing
    round-robin. ``use_case`` is one of {'purchase_request', 'sponsorship_form'};
    complaint never reads this table, so complaint CS assignment stays round-robin.
    See docs/plans/PLAN-procurement-cs-handoff-and-pinpoint-routing.md.
    """

    __tablename__ = "respond_contact_cs_routing"

    # String PK (migration 231 created this column as VARCHAR). Must NOT be the
    # pg UUID type or SQLAlchemy emits `WHERE id = :id::UUID`, which fails against
    # a varchar column ("operator does not exist: character varying = uuid").
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    respond_contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    cs_pic_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    use_case = Column(String(50), nullable=False)  # purchase_request | sponsorship_form | complaint | stock_inquiry
    is_active = Column(Boolean, default=True, nullable=False)
    # Generic predicate set: array of {field, operator, value}, AND-combined, evaluated
    # against the form header's own fields. Empty [] = wildcard (always matches). The
    # winning pin for a form = lowest `priority` among matching rows (created_at
    # tiebreak). See app.services.cs_routing_match.
    match_conditions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    priority = Column(Integer, nullable=False, server_default="0")  # lower wins (pure admin order)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)

    contact = relationship("RespondContact")
    cs_pic = relationship("User")

    __table_args__ = (
        # Uniqueness is (respond_contact_id, use_case, md5(match_conditions::text))
        # one pin per distinct condition-set per contact+use_case. It is an EXPRESSION
        # unique index (uq_cs_routing_contact_use_case_conditions), created in the
        # migration; SQLAlchemy can't model an md5(jsonb) expression index inline.
        Index("ix_cs_routing_contact", "respond_contact_id"),
        Index("ix_cs_routing_cs_pic", "cs_pic_user_id"),
    )


class AccessAgent(Base):
    __tablename__ = "access_agents"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    assign_to_new_internal_contacts = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)

    contact_accesses = relationship("ContactAgentAccess", back_populates="agent")
    agent_teams = relationship("AgentTeam", back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_access_agents_is_active", "is_active"),
        Index("ix_access_agents_code", "code"),
    )


class ContactAgentAccess(Base):
    __tablename__ = "contact_agent_access"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    respond_contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=True)  # FK to respond_contacts
    respond_contact_phone = Column(Text, nullable=False)  # Keep for backward compatibility
    respond_contact_name = Column(Text, nullable=True)  # Keep for backward compatibility
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    is_allowed = Column(Boolean, default=True, nullable=False)
    valid_from = Column(DateTime(timezone=False), nullable=True)
    valid_to = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    agent = relationship("AccessAgent", back_populates="contact_accesses")
    contact = relationship("RespondContact", back_populates="contact_accesses")
    
    __table_args__ = (
        Index("ix_contact_agent_access_agent_id", "agent_id"),
        Index("ix_contact_agent_access_respond_contact_id", "respond_contact_id"),
        Index("ix_contact_agent_access_respond_contact_phone", "respond_contact_phone"),
        # Unique constraint on respond_contact_id and agent_id to prevent duplicates
        # Note: This will be created via migration as a partial unique index to handle NULL values
    )


class AgentFieldAccess(Base):
    """Which fields an agent may reveal, and to whom.

    `ContactAgentAccess` says WHICH FUNCTIONS a contact may use. This says WHICH
    FIELDS each of those functions may reveal - one level finer, so a sensitive
    column can be added to an existing answer without minting a whole new agent
    and re-granting it to the 53 contacts who already hold the function.

    `contact_id` NULL = the agent-wide default, applying to everyone holding the
    agent. A row WITH a contact overrides that default for that one contact, in
    either direction (`is_allowed` true grants an exception, false revokes one).

    `agent_code` FKs to `access_agents.code` with ON UPDATE CASCADE rather than to
    the id: the code is what the resolver, the seeds and the docs all name, and a
    rename should carry the rows with it.

    Only fields registered in `app.services.field_access.GATED_FIELDS` are
    consulted; a row for anything else is inert. Absence of a row means DENY.
    """
    __tablename__ = "agent_field_access"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_code = Column(
        Text,
        ForeignKey("access_agents.code", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    #: Namespace for the field keys, so `eta_date` on incoming stock and a future
    #: `eta_date` on something else never collide.
    resource = Column(Text, nullable=False)
    field_key = Column(Text, nullable=False)
    #: NULL = applies to every contact holding the agent.
    contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=True
    )
    is_allowed = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(Text, nullable=True)
    #: Who last changed the tick. Separate from `created_by` because every row is
    #: pre-seeded denied by the bootstrap, so the insert never has a human behind
    #: it - `created_by` alone would be NULL on every grant anyone ever makes.
    updated_by = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_agent_field_access_lookup", "resource", "agent_code"),
        Index("ix_agent_field_access_contact_id", "contact_id"),
        # Two partial uniques, not one constraint: in Postgres NULLs are distinct,
        # so a plain UNIQUE over the four columns would happily allow a second
        # agent-wide row for the same field.
        Index(
            "uq_agent_field_access_default",
            "agent_code",
            "resource",
            "field_key",
            unique=True,
            postgresql_where=text("contact_id IS NULL"),
        ),
        Index(
            "uq_agent_field_access_override",
            "agent_code",
            "resource",
            "field_key",
            "contact_id",
            unique=True,
            postgresql_where=text("contact_id IS NOT NULL"),
        ),
    )


class Team(Base):
    """Team of users for round-robin assignment."""
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text(), nullable=True)
    # Self-FK for the team hierarchy: a member of a parent team can see + act on the
    # work of all descendant teams (any depth). NULL = top-level. SET NULL on delete
    # so removing a parent re-roots its children rather than cascading them away.
    parent_team_id = Column(
        UUID(as_uuid=False),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    agent_teams = relationship("AgentTeam", back_populates="team", cascade="all, delete-orphan")
    parent = relationship("Team", remote_side=[id], foreign_keys=[parent_team_id])

    __table_args__ = (
        Index("ix_teams_name", "name"),
        Index("ix_teams_parent_team_id", "parent_team_id"),
    )


class TeamMember(Base):
    """User membership in a team (ordered for round-robin)."""
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(100), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=True)
    # Per-team round-robin eligibility. Default true = receives auto-assignments.
    # Per-team (NOT per-user): a multi-team member can be RR-eligible in one team and
    # excluded in another. Governs AUTO distribution only - manual takeover/reassign
    # can still target an excluded member, and they still appear in Team Tasks.
    include_in_round_robin = Column(
        Boolean, default=True, nullable=False, server_default=text("true")
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="members")
    user = relationship("User", backref="team_memberships")
    # Many-to-many: this membership ↔ market segments it serves. Empty = serves
    # every contact (untagged member = serves all).
    market_segments = relationship(
        "MarketSegment",
        secondary=team_member_market_segments,
        order_by="MarketSegment.sort_order, MarketSegment.code",
    )

    __table_args__ = (
        Index("ix_team_members_team_id", "team_id"),
        Index("ix_team_members_user_id", "user_id"),
        Index("uq_team_members_team_user", "team_id", "user_id", unique=True),
    )


class AgentTeam(Base):
    """Link access agent to a team set code and optional tier (1=initial, 2/3=escalation)."""
    __tablename__ = "agent_teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)  # Team set code (e.g. marketing_product, retail_director)
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    tier = Column(Integer, nullable=True)  # Explicit tier: 1/2/3 within a team set
    # Conversation SLA policy bound to this team set. One policy per (agent, code),
    # cast to every tier row of the set by set_agent_teams. RESTRICT so a policy in
    # use can't be deleted (mirrors the SLA-policy delete guard).
    policy_id = Column(UUID(as_uuid=False), ForeignKey("sla_policies.id", ondelete="RESTRICT"), nullable=True)
    # Whether THIS tier's team is notified when a LOWER-tier SLA deadline is extended.
    # On extend, every higher tier (current+1..3) with this flag set gets a
    # "deadline extended" notice. Default true preserves+extends the old "+1 only"
    # behaviour (now the grandparent is reached too); admins untick to silence a tier.
    notify_on_extension = Column(
        Boolean, default=True, nullable=False, server_default=text("true")
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    agent = relationship("AccessAgent", back_populates="agent_teams")
    team = relationship("Team", back_populates="agent_teams")

    __table_args__ = (
        Index("ix_agent_teams_agent_id", "agent_id"),
        Index("ix_agent_teams_team_id", "team_id"),
        Index("ix_agent_teams_code", "code"),
        Index("ix_agent_teams_tier", "tier"),
        # For non-tier assignments (legacy), keep one row per (agent, code).
        Index(
            "uq_agent_teams_agent_code_tier_null",
            "agent_id",
            "code",
            unique=True,
            postgresql_where=(tier.is_(None)),
        ),
        # For tiered assignments, allow one row per (agent, code, tier).
        Index(
            "uq_agent_teams_agent_code_tier_not_null",
            "agent_id",
            "code",
            "tier",
            unique=True,
            postgresql_where=(tier.is_not(None)),
        ),
    )


class AgentTeamRoundRobinCursor(Base):
    """Per (agent, team) cursor for round-robin next assignee."""
    __tablename__ = "agent_team_round_robin_cursors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    # Market-segment discriminator for the rotation. '' = the legacy / no-segment
    # cursor (used when next-assignee gets no contact_id - unchanged behaviour).
    # Non-empty = sorted '|'-joined contact segment codes (e.g. 'project|retail').
    segment_key = Column(String(120), nullable=False, server_default=text("''"))
    last_assigned_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_team_rr_cursors_agent_team_segment", "agent_id", "team_id", "segment_key", unique=True),
    )


class McpTool(Base):
    """Persisted catalog row for one MCP tool. Synced from code catalog by
    `app.services.mcp_tool_registry_service.sync_catalog`.

    Pure catalog: the tool→agent ownership model was removed once n8n took over
    agent/team routing. Contact access is enforced per-agent only
    (`contact_agent_access` + `mcp_access_service.evaluate_agent`).
    """

    __tablename__ = "mcp_tools"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    module_key = Column(Text, nullable=False, default="", server_default="")
    http_path = Column(Text, nullable=False)
    http_method = Column(Text, nullable=False, default="GET", server_default="GET")
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime(timezone=False), nullable=False)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_mcp_tools_module_key", "module_key"),
        Index("ix_mcp_tools_is_active", "is_active"),
    )
