"""Access control models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
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
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    respond_mappings = relationship(
        "RespondAccessTypeMapping",
        back_populates="access_type",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_contact_access_types_is_active", "is_active"),
    )


class RespondAccessTypeMapping(Base):
    """Maps Respond.io raw values (e.g. custom field) to a configured contact_access_type code."""
    __tablename__ = "respond_access_type_mappings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_key = Column(String(255), nullable=False)  # Raw value from Respond (e.g. "Dealer", "End User")
    access_type_code = Column(String(50), ForeignKey("contact_access_types.code", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    access_type = relationship("ContactAccessType", back_populates="respond_mappings")

    __table_args__ = (
        Index("ix_respond_access_type_mappings_source_key", "source_key"),
        Index("ix_respond_access_type_mappings_access_type_code", "access_type_code"),
        Index("uq_respond_access_type_mappings_source_key", "source_key", unique=True),
    )


class RespondContact(Base):
    __tablename__ = "respond_contacts"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=True)
    user_type = Column(Text, nullable=True)  # Raw value from Respond; kept for display/sync
    access_type_code = Column(String(50), ForeignKey("contact_access_types.code", ondelete="SET NULL"), nullable=True)  # Resolved catalog code (one per contact)
    respond_io_id = Column(Text, nullable=True)  # Respond.io contact id for inbox URL
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)
    
    contact_accesses = relationship(
        "ContactAgentAccess",
        back_populates="contact",
        cascade="all, delete-orphan",
    )
    access_type = relationship("ContactAccessType", foreign_keys=[access_type_code])

    __table_args__ = (
        Index("ix_respond_contacts_phone_number", "phone_number"),
        Index("ix_respond_contacts_user_type", "user_type"),
        Index("ix_respond_contacts_access_type_code", "access_type_code"),
        Index("ix_respond_contacts_respond_io_id", "respond_io_id"),
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
    """Link access agent to a team with a context code and optional tier (1=initial, 2/3=escalation)."""
    __tablename__ = "agent_teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)  # Context code (e.g. marketing, tier_1, project_sales)
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    tier = Column(Integer, nullable=True)  # Explicit tier: 1=initial notifications, 2/3=escalation (one per agent)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    agent = relationship("AccessAgent", back_populates="agent_teams")
    team = relationship("Team", back_populates="agent_teams")

    __table_args__ = (
        Index("ix_agent_teams_agent_id", "agent_id"),
        Index("ix_agent_teams_team_id", "team_id"),
        Index("ix_agent_teams_code", "code"),
        Index("ix_agent_teams_tier", "tier"),
        Index("uq_agent_teams_agent_code", "agent_id", "code", unique=True),
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
