"""Access control models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Table, Text, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


# Join table — many-to-many between AccessAgent and McpTool.
agent_mcp_tools = Table(
    "agent_mcp_tools",
    Base.metadata,
    Column(
        "agent_id",
        UUID(as_uuid=False),
        ForeignKey("access_agents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tool_id",
        UUID(as_uuid=False),
        ForeignKey("mcp_tools.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    ),
    Index("ix_agent_mcp_tools_agent_id", "agent_id"),
    Index("ix_agent_mcp_tools_tool_id", "tool_id"),
)


class ContactAccessType(Base):
    """Configurable catalog for contact access types (e.g. end_user, dealer, sorento_dealer). Used for promotion/attachment visibility and contact classification."""
    __tablename__ = "contact_access_types"

    code = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, nullable=True)
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


class RespondContact(Base):
    __tablename__ = "respond_contacts"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=True)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    respond_io_id = Column(Text, nullable=True)  # Respond.io contact id for inbox URL
    workspace_id = Column(UUID(as_uuid=False), ForeignKey("respond_workspaces.id", ondelete="SET NULL"), nullable=True)
    # Per-conversation variables collected from n8n turns: {"turns":[{ts,inquiry_type,vars}], "merged":{<inquiry_type>:{...}}}.
    # Maintained by /api/v1/external/conversation-variables/upsert; sliding window capped per call.
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
    workspace = relationship("RespondWorkspace", back_populates="respond_contacts")

    __table_args__ = (
        Index("ix_respond_contacts_phone_number", "phone_number"),
        Index("ix_respond_contacts_respond_io_id", "respond_io_id"),
        Index("ix_respond_contacts_workspace_id", "workspace_id"),
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
    mcp_tools = relationship(
        "McpTool",
        secondary=agent_mcp_tools,
        back_populates="agents",
    )

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


class Team(Base):
    """Team of users for round-robin assignment."""
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    agent_teams = relationship("AgentTeam", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_teams_name", "name"),)


class TeamMember(Base):
    """User membership in a team (ordered for round-robin)."""
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(100), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="members")
    user = relationship("User", backref="team_memberships")

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
    last_assigned_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_agent_team_round_robin_cursors_agent_team", "agent_id", "team_id", unique=True),
    )


class McpTool(Base):
    """Persisted catalog row for one MCP tool. Synced from code catalog by
    `app.services.mcp_tool_registry_service.sync_catalog`.

    Ownership is many-to-many via ``agent_mcp_tools``. Sync NEVER touches
    ownership; only admins do.
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

    agents = relationship(
        "AccessAgent",
        secondary=agent_mcp_tools,
        back_populates="mcp_tools",
    )

    __table_args__ = (
        Index("ix_mcp_tools_module_key", "module_key"),
        Index("ix_mcp_tools_is_active", "is_active"),
    )


class McpAccessLog(Base):
    """One row per MCP access decision. Phase 1 defines the table; Phase 3's
    access-check endpoint is the only writer.
    """

    __tablename__ = "mcp_access_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name = Column(Text, nullable=False)
    contact_external_id = Column(Text, nullable=True)
    respond_contact_id = Column(Text, nullable=True)
    respond_workspace_id = Column(UUID(as_uuid=False), nullable=True)
    decision = Column(Text, nullable=False)
    matched_agent_id = Column(UUID(as_uuid=False), nullable=True)
    ts = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_mcp_access_log_ts", "ts"),
        Index("ix_mcp_access_log_tool_name", "tool_name"),
    )
