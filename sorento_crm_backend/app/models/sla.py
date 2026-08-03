"""SLA management models."""
from sqlalchemy import CheckConstraint, Column, String, Boolean, DateTime, ForeignKey, Text, Integer, BigInteger, Numeric, Index, text
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
    # Extend-deadline soft limits (PLAN-sla-extend-deadline). All nullable = no limit.
    # Breach is a warning only; the extension still applies.
    max_extension_days_per_request = Column(Integer, nullable=True)  # max working days per single extend
    max_extension_count = Column(Integer, nullable=True)             # max number of extends per tracker
    max_extension_days_total = Column(Numeric(10, 2), nullable=True) # max cumulative working days extended
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    # passive_deletes=True: rely on the DB-level ON DELETE CASCADE (sla_policy_tiers.policy_id)
    # instead of the ORM nulling child FKs before delete (which violates NOT NULL).
    tiers = relationship(
        "SLAPolicyTier",
        back_populates="policy",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
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
    # Numeric so sub-hour SLAs are expressible (e.g. 0.5 = 30 minutes).
    response_hours = Column(Numeric(6, 2), nullable=False)
    resolution_hours = Column(Numeric(6, 2), nullable=False, server_default="24")
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
    # Polymorphic (no FK) but always a uuid — see migration 300.
    source_entity_id = Column(UUID(as_uuid=False), nullable=True)
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="SET NULL"), nullable=True)  # FK to access_agents
    team_set_code = Column(String(100), nullable=True)  # Team assignment set code for escalation; cleared on resolve
    message_id = Column(BigInteger, nullable=True)  # External message id (e.g. n8n); cleared on resolve
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    resolution_duration = Column(Numeric(10, 2), nullable=True)
    # Extend-deadline denormalized counters (PLAN-sla-extend-deadline). The event log
    # is the immutable trail; these are fast-read for soft-limit checks + row chip.
    extension_count = Column(Integer, nullable=False, server_default=text("0"), default=0)
    extension_days_total = Column(Numeric(10, 2), nullable=False, server_default=text("0"), default=0)
    # Handling lock (PLAN-form-handling-lock). Once a FORM tracker is escalated
    # (current_tier > 1) the state-changing CTAs disable for everyone until an
    # eligible team-chain member claims the lock here. Separate from assigned_to_id:
    # claiming never reassigns and never de-escalates. NULL = unclaimed. Reset to NULL
    # on every re-escalation. Never set for conversation-SLA (n8n) rows.
    handled_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at = Column(DateTime(timezone=False), nullable=True)
    # AC-M33: this tracker was routed to the agent's configured assignment fallback
    # because nobody resolved at any tier. On the TRACKER and not on the case: the
    # pending-task row is a tracker, and a case-level column would paint one stage's
    # routing failure onto every other stage of the same case. NOT NULL with a
    # server default so every existing row stays readable after the migration —
    # "maybe unresolved" has no meaning.
    assignment_unresolved = Column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # S4a waiting attribution (AC-M1). On the TRACKER for the same reason as the flag
    # above: a case runs several stages at once and is not waiting on one party -
    # Schedule waits on the customer while Assess waits on maintenance. The
    # case-level answer is DERIVED from the case's open trackers (Ruling 1 in
    # PLAN-after-sales-warranty.md), never stored.
    #
    # Both store the lookup option's VALUE, not its id. AC-M1 names the field
    # `waiting_on_reason_id` and an id was the first shape built, but every bound
    # column in this system holds the value and `lookup_validator` enforces exactly
    # that on flush: an id-holding bound column is rejected by the generic validator
    # (`invalid_lookup_value`), gets no FE dropdown from the binding, and cannot be
    # mapped by POST /lookup/resolve. The value IS the stable identity - `label` is the
    # display text, and that is what admins reword - so history stays correct either
    # way. AC-M7 also groups breaches by party, which a text column does without a join.
    waiting_on_party = Column(String(150), nullable=True)
    waiting_on_reason = Column(String(150), nullable=True)
    # Set once per wait. Re-setting the SAME party (correcting the reason) must not
    # restart it, or "waiting on maintenance since 3 Aug" becomes "since just now".
    waiting_since = Column(DateTime(timezone=False), nullable=True)

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
        Index("ix_conversation_sla_tracking_handled_by_id", "handled_by_id"),
        Index(
            "ix_sla_tracking_waiting_party",
            "waiting_on_party",
            postgresql_where=text("waiting_on_party IS NOT NULL"),
        ),
        # AC-M3 renders "waiting on maintenance SINCE 3 Aug". A party with no
        # waiting_since renders half a sentence and a waiting_since with no party is a
        # wait on nobody, so both halves are enforced here rather than in the service -
        # the service is not the only writer a backfill or a fix-up script ever has.
        CheckConstraint(
            "(waiting_on_party IS NULL) = (waiting_since IS NULL)",
            name="ck_sla_tracking_waiting_party_pair",
        ),
        CheckConstraint(
            "waiting_on_reason IS NULL OR waiting_on_party IS NOT NULL",
            name="ck_sla_tracking_waiting_reason_needs_party",
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
    # Definition scope, for the one form type that has definitions. NULL = the stage
    # applies to EVERY definition of the type, which is what keeps the five
    # single-form types (complaint, PR, SF, stock_inquiry, ticket) untouched. Set = the
    # stage applies to that definition only, because `workflow_submission` is one type
    # covering an RMA form, a warranty claim and a satisfaction survey at once, and
    # start_event names status KEYS that forked definitions deliberately share.
    definition_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_form_definitions.id", ondelete="CASCADE"),
        nullable=True,
    )
    start_event = Column(String(100), nullable=False)
    respond_event = Column(String(100), nullable=True)
    resolve_event = Column(String(100), nullable=True)
    next_config_id = Column(
        UUID(as_uuid=False),
        ForeignKey("form_sla_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # When set, the next stage (next_config_id) is spawned ONLY when the resolve
    # was triggered by this specific event (e.g. 'approved' — so 'rejected' closes
    # the stage without advancing to customer service). NULL = spawn on any resolve
    # (backward-compatible with existing single-event chains).
    advance_on_event = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # When false, spawning this stage assigns the tracker but does NOT notify the
    # assignee (some stages route silently). Default true = notify on assignment.
    notify_assignee = Column(Boolean, default=True, nullable=False, server_default=text("true"))
    # When false, escalating a tracker on this stage does NOT notify the new assignee
    # (silent escalation). Default true = notify on escalation.
    notify_on_escalation = Column(Boolean, default=True, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    policy = relationship("SLAPolicy", foreign_keys=[policy_id])
    next_config = relationship("FormSLAConfig", remote_side=[id], foreign_keys=[next_config_id])

    __table_args__ = (
        Index("ix_form_sla_configs_source_entity_type", "source_entity_type"),
        Index("ix_form_sla_configs_policy_id", "policy_id"),
        Index("ix_form_sla_configs_definition_id", "definition_id"),
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
    # Escalated-FROM owner: the assignee at the PRIOR tier, snapshotted at escalation
    # time BEFORE assigned_to_id is overwritten to the new tier's assignee. The
    # escalation banner links this person (who missed). NULL for non-escalation events.
    from_assigned_to_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # FK to users
    due_at = Column(DateTime(timezone=False), nullable=True)
    response_time = Column(Numeric(10, 2), nullable=True)
    resolution_time = Column(Numeric(10, 2), nullable=True)
    reminder_count = Column(Integer, default=0, nullable=False)
    last_reminder_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    # How an escalation fired: 'auto' (overdue scan) or 'manual' (user-triggered, TCK-28).
    trigger = Column(String(16), nullable=False, server_default="auto")
    # The human who triggered a manual escalation (NULL for auto). NOT the assignee.
    triggered_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # S4a point-in-time capture (AC-M7). Stamped by create_event_log from the
    # tracker's LIVE values at the instant of the event, so reporting reads what we
    # were waiting on WHEN it breached. Reading the tracker column instead would
    # re-attribute every historical breach the next time somebody edits the case.
    waiting_on_party = Column(String(150), nullable=True)
    waiting_on_reason = Column(String(150), nullable=True)
    waiting_since = Column(DateTime(timezone=False), nullable=True)

    tracking = relationship("ConversationSLATracking", back_populates="event_logs")
    assigned_user = relationship("User", foreign_keys=[assigned_to_id])
    
    __table_args__ = (
        Index("ix_conversation_sla_event_log_sla_tracking_id", "sla_tracking_id"),
        Index("ix_conversation_sla_event_log_event_at", "event_at"),
        Index("ix_conversation_sla_event_log_event_type", "event_type"),
        Index("ix_conversation_sla_event_log_assigned_to_id", "assigned_to_id"),
        Index("ix_conversation_sla_event_log_from_assigned_to_id", "from_assigned_to_id"),
        Index(
            "ix_sla_event_log_waiting_party",
            "waiting_on_party",
            postgresql_where=text("waiting_on_party IS NOT NULL"),
        ),
    )


# Handling-lock event_type values on ConversationSLAEventLog (PLAN-form-handling-lock).
# assigned_to_id = the handler at the time, triggered_by_id = the actor, reason = context.
HANDLING_CLAIMED = "handling_claimed"
HANDLING_TAKEN_OVER = "handling_taken_over"
HANDLING_RELEASED = "handling_released"


# Takeover request lifecycle statuses (see PLAN-takeover-cooldown).
TAKEOVER_PENDING = "pending"
TAKEOVER_COMMITTED = "committed"
TAKEOVER_CANCELLED = "cancelled"
TAKEOVER_REJECTED = "rejected"
TAKEOVER_VOIDED = "voided"
TAKEOVER_TERMINAL = (TAKEOVER_COMMITTED, TAKEOVER_CANCELLED, TAKEOVER_REJECTED, TAKEOVER_VOIDED)


class SlaTakeoverRequest(Base):
    """A pending-intent takeover with a cooldown veto window.

    Initiator clicks Takeover -> a `pending` row is created with `commit_at = now +
    cooldown`. Nothing about the SLA assignment changes until commit. During the
    window the original assignee can Reject, the initiator can Cancel, and any owner
    terminal action (resolve/reassign/escalate) voids it. The scheduler sweep commits
    unchallenged rows past `commit_at`. Terminal rows are retained for audit; a partial
    unique index allows at most ONE pending row per tracking. See PLAN-takeover-cooldown.
    """

    __tablename__ = "sla_takeover_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tracking_id = Column(
        UUID(as_uuid=False),
        ForeignKey("conversation_sla_tracking.id", ondelete="CASCADE"),
        nullable=False,
    )
    initiator_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Snapshot of the assignee being contested at create time (NULL = task was unassigned).
    contested_assignee_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Queue team context the row was shown under — drives tier re-derivation at commit.
    team_id = Column(UUID(as_uuid=False), nullable=False)
    status = Column(String(16), nullable=False, server_default=TAKEOVER_PENDING)
    commit_at = Column(DateTime(timezone=False), nullable=False)  # naive UTC
    resolution_reason = Column(String(32), nullable=True)  # cancel|reject|resolved|escalated|reassigned|committed|ineligible
    resolved_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=False), nullable=True)

    tracking = relationship("ConversationSLATracking")
    initiator = relationship("User", foreign_keys=[initiator_id])
    contested_assignee = relationship("User", foreign_keys=[contested_assignee_id])

    __table_args__ = (
        Index("ix_sla_takeover_requests_tracking_id", "tracking_id"),
        Index("ix_sla_takeover_requests_status_commit_at", "status", "commit_at"),
        # At most one pending takeover per tracking.
        Index(
            "uq_sla_takeover_requests_one_pending",
            "tracking_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
