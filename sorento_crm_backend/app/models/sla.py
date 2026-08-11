"""SLA management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, BigInteger, Numeric, Index, text
from sqlalchemy.dialects.postgresql import JSONB as JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

# Forward reference: AccessAgent is defined in app.models.access


class SLAPolicy(Base):
    """An SLA policy belongs to one company (D5) via its NOT NULL ``company_id``.

    Deliberately NOT a CompanyScopedMixin. Making it one auto-filters and
    auto-stamps every policy read and write in the product, which broke ~160 tests
    covering escalation, extension, takeover and the daily summary - paths that
    legitimately read a policy with no active company (scheduler ticks, form-SLA
    fixtures). Isolation where it actually matters is enforced in two narrower
    places: the picker query filters by the active company, and the agent_teams
    (policy_id, company_id) composite FK rejects a cross-company binding outright.

    ``code`` is unique per company, not globally: migration 320 dropped
    sla_policies_code_key in favour of (code, company_id).
    """

    __tablename__ = "sla_policies"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(Text, nullable=False)
    # Mapped WITHOUT CompanyScopedMixin (see the class docstring): the column is real
    # (migration 320, NOT NULL with a Sorento server default) and the picker filters
    # on it, but no auto-filter or auto-stamp is wanted here.
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=True, index=True)
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
    # The company this tracker escalates within. Stamped once at creation from the
    # contact (conversation SLA) or the spawning entity's contact (form SLA), then
    # read back by every escalation. NOT a CompanyScopedMixin: escalation runs from
    # scheduler ticks and cross-company admin views that must still see the row —
    # the company governs which ladder is climbed, not who may read the tracker.
    # ORM-nullable / PG-NOT-NULL on purpose, matching the mixin's convention: the
    # scratch-schema fixtures insert before any stamp would fire.
    # Python-side default, not just the migration's server default: the ORM emits the
    # column as an explicit NULL when a constructor omits it, so the server default
    # never fires and the insert dies on NOT NULL. Sorento is the documented fallback
    # for a tracker with no resolvable company anyway (a ticket has no contact at
    # all), so defaulting here matches what the resolvers would have produced.
    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id"),
        nullable=True,
        index=True,
        default="00000000-0000-0000-0000-000000000001",
    )
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
    # When set, the next stage (next_config_id) is spawned ONLY when the resolve
    # was triggered by this specific event (e.g. 'approved' — so 'rejected' closes
    # the stage without advancing to customer service). NULL = spawn on any resolve
    # (backward-compatible with existing single-event chains).
    advance_on_event = Column(String(100), nullable=True)
    # --- Undo grace window (PLAN-form-sla-undo.md) ---------------------------- #
    # Seconds an in-app action on this stage waits before it actually runs, so the
    # actor can take it back before anyone is told. NULL = use the global
    # `system_settings.form_sla_grace_seconds` (which ships as 0 = no deferral).
    grace_seconds = Column(Integer, nullable=True)
    # --- Skip the rest of the chain (UAC-form-sla-skip-stage) ---------------- #
    # When set, this stage may be closed by an explicit "skip" action instead of its
    # normal resolve: the stage resolves, the next stage never spawns, and the entity
    # jumps to `skip_terminal_status`. NULL `skip_event` = unskippable (the default,
    # and exactly today's behaviour).
    #
    # `skip_event` MUST also appear in `resolve_event` and MUST NOT appear in
    # `advance_on_event` - that pairing is what resolves the stage without advancing.
    skip_event = Column(String(100), nullable=True)
    # Terminal status written onto the entity. The adapter owns HOW to write it; this
    # column only says WHAT. Per-entity by design: 'settled_on_site' for a complaint.
    skip_terminal_status = Column(String(100), nullable=True)
    # Label for the gear-menu item ("Settled on site"). Config supplies the label only;
    # the consequence sentence shown in the confirm dialog is domain truth and comes
    # from the adapter, never from here.
    skip_action_label = Column(String(120), nullable=True)
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

    tracking = relationship("ConversationSLATracking", back_populates="event_logs")
    assigned_user = relationship("User", foreign_keys=[assigned_to_id])
    
    __table_args__ = (
        Index("ix_conversation_sla_event_log_sla_tracking_id", "sla_tracking_id"),
        Index("ix_conversation_sla_event_log_event_at", "event_at"),
        Index("ix_conversation_sla_event_log_event_type", "event_type"),
        Index("ix_conversation_sla_event_log_assigned_to_id", "assigned_to_id"),
        Index("ix_conversation_sla_event_log_from_assigned_to_id", "from_assigned_to_id"),
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


# ---------------------------------------------------------------------------
# Form SLA Undo (PLAN-form-sla-undo.md)
# ---------------------------------------------------------------------------

FORM_ACTION_PENDING = "pending"
FORM_ACTION_COMMITTED = "committed"
FORM_ACTION_CANCELLED = "cancelled"
FORM_ACTION_INELIGIBLE = "ineligible"
FORM_ACTION_FAILED = "failed"
FORM_ACTION_UNDONE = "undone"
FORM_ACTION_TERMINAL = (
    FORM_ACTION_COMMITTED,
    FORM_ACTION_CANCELLED,
    FORM_ACTION_INELIGIBLE,
    FORM_ACTION_FAILED,
    FORM_ACTION_UNDONE,
)

# Channel decides whether an action may defer at all. Only an in-system UI caller can
# be shown an Undo button, so only `ui` ever waits out a grace window; portal /
# API-key / n8n / MCP callers execute immediately and keep today's response shapes.
FORM_ACTION_CHANNEL_UI = "ui"
FORM_ACTION_CHANNEL_IMMEDIATE = "immediate"


class SlaFormAction(Base):
    """A form-SLA action that either waits out a grace window before running, or ran
    immediately and is retained as the undo history.

    Deliberately mirrors ``SlaTakeoverRequest``'s lifecycle vocabulary. Committed rows
    are never deleted - they are what a post-grace undo reads to restore prior state.
    """

    __tablename__ = "sla_form_actions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_key = Column(String(64), nullable=False)
    source_entity_type = Column(String(50), nullable=False)
    source_entity_id = Column(UUID(as_uuid=False), nullable=False)
    # The resolve-event this action will emit — the guardrail reads it to find the
    # stage the action closed.
    event_name = Column(String(64), nullable=True)

    # Arguments for the registry's `execute`, and the domain columns it is about to
    # overwrite, captured BEFORE it runs. The inverse restores from this snapshot and
    # never from a guessed default.
    payload_json = Column(JSON, nullable=False, default=dict)
    prior_state_json = Column(JSON, nullable=False, default=dict)

    requested_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    channel = Column(String(16), nullable=False, server_default=FORM_ACTION_CHANNEL_IMMEDIATE)
    status = Column(String(16), nullable=False, server_default=FORM_ACTION_PENDING)

    commit_at = Column(DateTime(timezone=False), nullable=True)  # naive UTC
    committed_at = Column(DateTime(timezone=False), nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolution_reason = Column(String(32), nullable=True)
    error_text = Column(Text, nullable=True)

    # The stage tracker this action resolved (reopen target) and the one its commit
    # spawned (void target). Not FKs: a tracker can be hard-deleted, and losing the
    # history row with it would be worse than a dangling id.
    prior_tracking_id = Column(UUID(as_uuid=False), nullable=True)
    spawned_tracking_id = Column(UUID(as_uuid=False), nullable=True)

    undone_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    undone_at = Column(DateTime(timezone=False), nullable=True)
    undo_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_sla_form_actions_sweep", "status", "commit_at"),
        Index(
            "ix_sla_form_actions_last",
            "source_entity_type",
            "source_entity_id",
            "committed_at",
        ),
        # At most one pending action per form row (AC-D-7). A second action attempted
        # while one is pending is refused by the database, not only by the service.
        Index(
            "uq_sla_form_actions_one_pending",
            "source_entity_type",
            "source_entity_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
