"""SLA management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, BigInteger, Numeric, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

# Forward reference: AccessAgent is defined in app.models.access


class SLAPolicy(Base):
    __tablename__ = "sla_policies"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    tiers = relationship("SLAPolicyTier", back_populates="policy")
    tracking = relationship("ConversationSLATracking", back_populates="policy")
    
    __table_args__ = (
        Index("ix_sla_policies_is_active", "is_active"),
        Index("ix_sla_policies_code", "code"),
    )


class SLAPolicyTier(Base):
    __tablename__ = "sla_policy_tiers"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(UUID(as_uuid=False), ForeignKey("sla_policies.id", ondelete="CASCADE"), nullable=False)
    tier_level = Column(Integer, nullable=False)
    tier_name = Column(Text, nullable=False)
    response_hours = Column(Integer, nullable=False)
    resolution_hours = Column(Integer, nullable=False, server_default="24")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    policy = relationship("SLAPolicy", back_populates="tiers")
    
    __table_args__ = (
        Index("ix_sla_policy_tiers_policy_id", "policy_id"),
        Index("uq_sla_policy_tiers_policy_id_tier_level", "policy_id", "tier_level", unique=True),
    )


class ConversationSLATracking(Base):
    __tablename__ = "conversation_sla_tracking"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(UUID(as_uuid=False), ForeignKey("sla_policies.id"), nullable=False)
    current_tier = Column(Integer, nullable=False)
    assigned_to = Column(Text, nullable=True)  # Keep for backward compatibility
    assigned_to_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # FK to users
    initiated_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    current_tier_started_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    due_at = Column(DateTime(timezone=False), nullable=False)  # Response deadline: current_tier_started_at + tier.response_hours
    due_at_resolution = Column(DateTime(timezone=False), nullable=True)  # Resolution deadline: current_tier_started_at + tier.resolution_hours
    escalated_at = Column(DateTime(timezone=False), nullable=True)
    escalation_reason = Column(Text, nullable=True)
    is_responded = Column(Boolean, default=False, nullable=False)
    responded_at = Column(DateTime(timezone=False), nullable=True)
    responded_by = Column(Text, nullable=True)
    response_time = Column(Numeric(10, 2), nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    respond_contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True)  # FK to respond_contacts
    source_entity_type = Column(String(50), nullable=True)  # stock_inquiry | complaint
    source_entity_id = Column(String(100), nullable=True)
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="SET NULL"), nullable=True)  # FK to access_agents
    team_set_code = Column(String(100), nullable=True)  # Team assignment set code for escalation; cleared on resolve
    message_id = Column(BigInteger, nullable=True)  # External message id (e.g. n8n); cleared on resolve
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    resolution_duration = Column(Numeric(10, 2), nullable=True)
    
    policy = relationship("SLAPolicy", back_populates="tracking")
    event_logs = relationship(
        "ConversationSLAEventLog",
        back_populates="tracking",
        cascade="all, delete-orphan",
    )
    contact = relationship("RespondContact", foreign_keys=[respond_contact_id])
    assigned_user = relationship("User", foreign_keys=[assigned_to_id])
    agent = relationship("AccessAgent", foreign_keys=[agent_id])
    
    __table_args__ = (
        Index("ix_conversation_sla_tracking_policy_id", "policy_id"),
        Index("ix_conversation_sla_tracking_is_resolved", "is_resolved"),
        Index("ix_conversation_sla_tracking_assigned_to", "assigned_to"),
        Index("ix_conversation_sla_tracking_assigned_to_id", "assigned_to_id"),
        Index("ix_conversation_sla_tracking_respond_contact_id", "respond_contact_id"),
        Index("ix_conversation_sla_tracking_agent_id", "agent_id"),
        # Hot path: get_tracking_by_source_entity filters on this pair for every
        # stock-inquiry / complaint reply.
        Index(
            "ix_conversation_sla_tracking_source_entity",
            "source_entity_type",
            "source_entity_id",
        ),
    )


class FormSLAConfig(Base):
    """Per-form-type SLA stage configuration. One row = one stage of one form's SLA pipeline.

    Multiple rows per source_entity_type model multi-stage chains
    (e.g. stock_inquiry: stage `project_sales` -> stage `purchasing`).
    `next_config_id` links current stage to the next stage to spawn on resolve.
    """

    __tablename__ = "form_sla_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_type = Column(String(50), nullable=False)
    stage_code = Column(String(100), nullable=False)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("sla_policies.id", ondelete="RESTRICT"), nullable=False)
    agent_code = Column(String(100), nullable=False)
    team_set_code = Column(String(100), nullable=True)
    start_event = Column(String(100), nullable=False)
    respond_event = Column(String(100), nullable=True)
    resolve_event = Column(String(100), nullable=True)
    next_config_id = Column(
        UUID(as_uuid=False),
        ForeignKey("form_sla_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    policy = relationship("SLAPolicy", foreign_keys=[policy_id])
    next_config = relationship("FormSLAConfig", remote_side=[id], foreign_keys=[next_config_id])

    __table_args__ = (
        Index("ix_form_sla_configs_source_entity_type", "source_entity_type"),
        Index("ix_form_sla_configs_policy_id", "policy_id"),
    )


class ConversationSLAEventLog(Base):
    __tablename__ = "conversation_sla_event_log"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    sla_tracking_id = Column(UUID(as_uuid=False), ForeignKey("conversation_sla_tracking.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(Text, nullable=False)  # escalation, response, resolution
    from_tier = Column(Integer, nullable=True)
    to_tier = Column(Integer, nullable=True)
    event_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)  # Stored without time zone
    from_time = Column(DateTime(timezone=False), nullable=True)  # Stored without time zone
    duration = Column(Numeric(10, 2), nullable=True)  # Duration in hours
    reason = Column(Text, nullable=True)
    assigned_to = Column(Text, nullable=True)  # Keep for backward compatibility
    assigned_to_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # FK to users
    due_at = Column(DateTime(timezone=False), nullable=True)
    response_time = Column(Numeric(10, 2), nullable=True)
    resolution_time = Column(Numeric(10, 2), nullable=True)
    reminder_count = Column(Integer, default=0, nullable=False)
    last_reminder_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    tracking = relationship("ConversationSLATracking", back_populates="event_logs")
    assigned_user = relationship("User", foreign_keys=[assigned_to_id])
    
    __table_args__ = (
        Index("ix_conversation_sla_event_log_sla_tracking_id", "sla_tracking_id"),
        Index("ix_conversation_sla_event_log_event_at", "event_at"),
        Index("ix_conversation_sla_event_log_event_type", "event_type"),
        Index("ix_conversation_sla_event_log_assigned_to_id", "assigned_to_id"),
    )
