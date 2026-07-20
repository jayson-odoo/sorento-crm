"""User management models."""
import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class UserStatus(str, enum.Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class User(Base):
    __tablename__ = "users"
    __audit_track__ = True  # who changed what (Sub-plan D Tier-2)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=True)
    country = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    name = Column(String, nullable=True)
    # Optional phone number used for user contact.
    contact_number = Column(String, nullable=True)
    status = Column(String, default=UserStatus.INACTIVE.value, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_sign_in_at = Column(DateTime(timezone=False), nullable=True)
    email_verified_at = Column(DateTime(timezone=False), nullable=True)
    is_trashed = Column(Boolean, default=False, nullable=False)
    avatar = Column(String, nullable=True)
    # Mirrors attachments.storage_provider: 's3' (S3 + CloudFront) or 'r2' (Cloudflare R2 + CDN).
    avatar_storage_provider = Column(String(16), nullable=False, server_default="s3")
    invited_by_user_id = Column(String, nullable=True)
    is_protected = Column(Boolean, default=False, nullable=False)
    respond_user_id = Column(String, nullable=True)
    respond_synced = Column(String, default="pending", nullable=False)
    superior_id = Column(String, ForeignKey("users.id"), nullable=True)
    tier = Column(Integer, nullable=True)  # Conversation SLA policy tier (1, 2, ...)
    daily_sla_summary_subscribed = Column(Boolean, default=True, nullable=False)  # email summary opt-in
    # Link to the WhatsApp contact this user is reachable on (resolves respond_io_id).
    # Set explicitly by an admin, or auto-cached by a unique phone match (see respond_link_service).
    respond_contact_id = Column(String, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True)
    # Per-channel notification toggles (default off until a contact is linked).
    notify_whatsapp = Column(Boolean, default=False, nullable=False, server_default="false")  # legacy; superseded by the per-event toggles below
    notify_whatsapp_summary = Column(Boolean, default=False, nullable=False, server_default="false")  # daily summary template
    # Per-event × per-channel SLA-notification toggles. A channel fires only when the
    # stage allows the event (form_sla_configs.notify_assignee / notify_on_escalation)
    # AND the user opted into that channel for that event. Email defaults on (preserves
    # prior always-email behaviour); WhatsApp backfilled from notify_whatsapp.
    notify_email_on_assignment = Column(Boolean, default=True, nullable=False, server_default="true")
    notify_email_on_escalation = Column(Boolean, default=True, nullable=False, server_default="true")
    notify_whatsapp_on_assignment = Column(Boolean, default=False, nullable=False, server_default="false")
    notify_whatsapp_on_escalation = Column(Boolean, default=False, nullable=False, server_default="false")
    # Product-discontinued batch notification opt-in (admin-configured per user). A user
    # with EITHER toggle on is a recipient (in-app always fires for recipients; email /
    # whatsapp each gated by its toggle). Both off => not a recipient, gets nothing.
    notify_email_on_product_discontinued = Column(Boolean, default=False, nullable=False, server_default="false")
    notify_whatsapp_on_product_discontinued = Column(Boolean, default=False, nullable=False, server_default="false")
    # SLA extend-deadline notification opt-ins (PLAN-sla-extend-deadline). Recipient is
    # the NEXT escalation tier assignee. Email defaults on; WhatsApp off (mirrors the
    # assignment/escalation toggle defaults). In-app always fires.
    notify_email_on_deadline_extended = Column(Boolean, default=True, nullable=False, server_default="true")
    notify_whatsapp_on_deadline_extended = Column(Boolean, default=False, nullable=False, server_default="false")
    # Form handling-lock notification opt-ins (PLAN-form-handling-lock). Recipients are
    # the affected parties (assignee / other eligible members / displaced holder) minus
    # the actor. Email defaults on; WhatsApp off (mirrors the assignment defaults). In-app
    # always fires for non-actor recipients.
    notify_email_on_handling = Column(Boolean, default=True, nullable=False, server_default="true")
    notify_whatsapp_on_handling = Column(Boolean, default=False, nullable=False, server_default="false")

    role_assignments = relationship("UserRoleAssignment", back_populates="user", cascade="all, delete-orphan")
    system_logs = relationship("SystemLog", back_populates="user")
    superior = relationship("User", remote_side=[id], backref="subordinates")
    quick_access = relationship("UserQuickAccess", back_populates="user", order_by="UserQuickAccess.sort_order")
    list_column_configs = relationship(
        "UserListColumnConfig",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("users_invited_by_user_id_idx", "invited_by_user_id"),
        Index("users_status_idx", "status"),
        Index("users_respond_synced_idx", "respond_synced"),
        Index("ix_users_respond_contact_id", "respond_contact_id"),
        # One phone == one user. Postgres allows multiple NULLs, so unlinked users are fine.
        UniqueConstraint("contact_number", name="uq_users_contact_number"),
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_trashed = Column(Boolean, default=False, nullable=False)
    created_by_user_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    is_protected = Column(Boolean, default=False, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    user_assignments = relationship("UserRoleAssignment", back_populates="role", cascade="all, delete-orphan")
    permissions = relationship(
        "UserRolePermission",
        back_populates="role",
        passive_deletes=True,
    )


class UserRoleAssignment(Base):
    """Pivot: user can have multiple roles. Kept in sync with users.role_id for compatibility."""
    __tablename__ = "user_role_assignments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String, ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="role_assignments")
    role = relationship("UserRole", back_populates="user_assignments")

    __table_args__ = (
        Index("ix_user_role_assignments_user_id", "user_id"),
        Index("ix_user_role_assignments_role_id", "role_id"),
        Index("uq_user_role_assignments_user_id_role_id", "user_id", "role_id", unique=True),
    )


class UserPermission(Base):
    __tablename__ = "user_permissions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by_user_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    roles = relationship("UserRolePermission", back_populates="permission")


class UserRolePermission(Base):
    __tablename__ = "user_role_permissions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String, ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(String, ForeignKey("user_permissions.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    role = relationship("UserRole", back_populates="permissions")
    permission = relationship("UserPermission", back_populates="roles")
    
    __table_args__ = (
        Index("user_role_permissions_role_id_permission_id_key", "role_id", "permission_id", unique=True),
    )


class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    entity_id = Column(String, nullable=True)
    entity_type = Column(String, nullable=True)
    event = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    meta = Column(Text, nullable=True)
    
    user = relationship("User", back_populates="system_logs")
    
    __table_args__ = (
        Index("system_logs_user_id_idx", "user_id"),
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"
    # id as String so UPDATE/WHERE work when DB column is TEXT (avoids "operator does not exist: text = uuid")
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, default="My Company", nullable=False)
    logo = Column(String, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    address = Column(Text, nullable=True)
    website_url = Column(String, nullable=True)
    support_email = Column(String, nullable=True)
    support_phone = Column(String, nullable=True)
    language = Column(String, default="en", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    currency = Column(String, default="MYR", nullable=False)
    currency_format = Column(String, default="RM {value}", nullable=False)
    
    social_facebook = Column(String, nullable=True)
    social_twitter = Column(String, nullable=True)
    social_instagram = Column(String, nullable=True)
    social_linkedin = Column(String, nullable=True)
    social_pinterest = Column(String, nullable=True)
    social_youtube = Column(String, nullable=True)
    
    notify_stock_email = Column(Boolean, default=True, nullable=False)
    notify_stock_web = Column(Boolean, default=True, nullable=False)
    notify_stock_threshold = Column(String, default="10", nullable=False)
    notify_stock_role_ids = Column(ARRAY(String), nullable=True)
    notify_new_order_email = Column(Boolean, default=True, nullable=False)
    notify_new_order_web = Column(Boolean, default=True, nullable=False)
    notify_new_order_role_ids = Column(ARRAY(String), nullable=True)
    notify_order_status_update_email = Column(Boolean, default=True, nullable=False)
    notify_order_status_update_web = Column(Boolean, default=True, nullable=False)
    notify_order_status_update_role_ids = Column(ARRAY(String), nullable=True)
    notify_payment_failure_email = Column(Boolean, default=True, nullable=False)
    notify_payment_failure_web = Column(Boolean, default=True, nullable=False)
    notify_payment_failure_role_ids = Column(ARRAY(String), nullable=True)
    notify_system_error_failure_email = Column(Boolean, default=True, nullable=False)
    notify_system_error_web = Column(Boolean, default=True, nullable=False)
    notify_system_error_role_ids = Column(ARRAY(String), nullable=True)

    # Complaint <-> DO auto-fulfilment: which Complaint-team tiers (Access-Agent
    # `complaint`, set `complaint`) receive the replacement-DO-delivered email/in-app.
    # Comma list of tier numbers, e.g. "1,2" (Tier 1 + Tier 2) or "1" (Tier 1 only).
    complaint_do_delivered_notify_tiers = Column(
        String(20), nullable=False, server_default="1,2", default="1,2"
    )

    # SMTP for notification emails (password not returned in read APIs)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(String(10), nullable=True)
    smtp_secure = Column(Boolean, default=True, nullable=False)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    smtp_from = Column(String(255), nullable=True)  # sender address or "Name <email>"

    # Takeover cooldown: seconds between a takeover confirm and the actual reassignment,
    # during which the original assignee can reject and the initiator can cancel.
    # 0 = disabled (takeover commits instantly, pre-feature behavior). See PLAN-takeover-cooldown.
    takeover_cooldown_seconds = Column(Integer, nullable=False, server_default="60", default=60)

    # System-health observability (PLAN-system-health-observability):
    # daily digest + immediate watchdog alerts. Recipients = role ids (like notify_*_role_ids).
    health_digest_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    health_alerts_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    health_notify_role_ids = Column(ARRAY(String), nullable=True)  # digest + alert recipients (by role); empty -> admins fallback in code
    health_notify_user_ids = Column(ARRAY(String), nullable=True)  # digest + alert recipients (individual users), unioned with role members
    health_integration_fail_threshold = Column(Integer, nullable=False, server_default="10", default=10)  # per-channel 24h failed spike
    health_audit_volume_floor = Column(Integer, nullable=False, server_default="0", default=0)  # 0 = floor alert disabled
    # Default overdue tolerance for scheduled tasks, as a percentage of each task's own
    # interval. Clamped to [60s, 30min] so it degrades sanely from a 30s task to a daily
    # one. Per-task override lives in scheduled_tasks.metadata->>'grace_percent'.
    health_task_grace_percent = Column(Integer, nullable=False, server_default="25", default=25)
    # WhatsApp round-trip SLA: user presses send -> our reply is accepted by Respond.
    # The clock stops at "sent", not delivered — see chat_latency_service.
    chat_latency_p99_target_seconds = Column(Integer, nullable=False, server_default="10", default=10)
    # A single turn past target x this multiplier alerts on its own, with no minimum
    # sample size: at volume, one stalled turn would never move a windowed percentile.
    chat_latency_ceiling_multiplier = Column(Integer, nullable=False, server_default="3", default=3)
    # An incoming with no reply after this long is the shape a dropped webhook takes —
    # the turn never completes, so it never enters the latency distribution at all.
    chat_latency_no_reply_minutes = Column(Integer, nullable=False, server_default="5", default=5)
    # Below this many paired turns a window percentile is noise, so fleet-level
    # breach alerting stays quiet.
    chat_latency_min_sample = Column(Integer, nullable=False, server_default="30", default=30)
    # My Downloads retention. Nothing purged this table before chat-history CSV exports
    # made the storage cost real; the purge applies to every download kind.
    downloads_retention_days = Column(Integer, nullable=False, server_default="30", default=30)

    # New products / import: default product_supplier (standard lead time + supplier)
    default_product_supplier_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_product_standard_lead_time_days = Column(Integer, nullable=False, server_default="90", default=90)

    # n8n integration (optional; attachment URL falls back to N8N_WEBHOOK_URL env if unset)
    n8n_attachment_webhook_url = Column(Text, nullable=True)
    n8n_crm_chat_outbound_webhook_url = Column(Text, nullable=True)
    n8n_stock_inquiry_revise_webhook_url = Column(Text, nullable=True)

    # Procurement: when set, "Send for approval" can skip the approver dialog and email the default user.
    purchase_request_default_approver_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sponsorship_form_default_approver_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Email guardrail thresholds: global + per-recipient caps + drainer cadence.
    # Tune below the SMTP provider's documented limits to prevent mail-server flagging.
    email_global_rate_per_window = Column(Integer, nullable=False, server_default="60", default=60)
    email_global_window_seconds = Column(Integer, nullable=False, server_default="60", default=60)
    email_per_recipient_rate_per_window = Column(Integer, nullable=False, server_default="10", default=10)
    email_per_recipient_window_seconds = Column(Integer, nullable=False, server_default="3600", default=3600)
    email_outbox_drain_batch_size = Column(Integer, nullable=False, server_default="20", default=20)
    email_outbox_drain_interval_seconds = Column(Integer, nullable=False, server_default="5", default=5)

    # AI assistant per-turn trace (M2) retention + payload caps. Swept by the
    # background scheduler: `ok` traces past ttl_days; `error`/`flagged` past
    # error_ttl_days. Payloads truncated at max_payload_bytes each.
    ai_trace_ttl_days = Column(Integer, nullable=False, server_default="30", default=30)
    ai_trace_error_ttl_days = Column(Integer, nullable=False, server_default="90", default=90)
    ai_trace_max_payload_bytes = Column(Integer, nullable=False, server_default="16384", default=16384)
    # M2.5 role split: when true, the agent loop runs an explicit planner node up
    # front and compresses raw tool JSON via the semantic_compressor node before
    # feeding it back. Default off — behavioral change, opt-in per PLAN Q7.
    ai_assistant_role_split_enabled = Column(Boolean, nullable=False, server_default="false", default=False)

    # Form handling-lock (PLAN-form-handling-lock): CSV of the source_entity_types the
    # lock is enabled for (e.g. "complaint,purchase_request"). Empty = off for every form
    # = today's status+permission-only gating. Read via
    # handling_lock_service.is_handling_lock_enabled.
    handling_lock_enabled_types = Column(Text, nullable=True, server_default="")


class UserQuickAccess(Base):
    """Per-user quick access (pinned menu items and attachment folders) for sidebar."""
    __tablename__ = "user_quick_access"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    path = Column(String(500), nullable=False)
    label = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="quick_access")

    __table_args__ = (
        Index("ix_user_quick_access_user_id", "user_id"),
        Index("ix_user_quick_access_user_id_path", "user_id", "path", unique=True),
    )


class UserListColumnConfig(Base):
    """Per-user per-listing column preferences (visibility + ordering)."""

    __tablename__ = "user_list_column_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Stable key identifying the listing.
    # In this implementation it is expected to be the RBAC view permission slug.
    listing_key = Column(String(255), nullable=False)

    # JSON payload:
    # - version: int
    # - columnOrder: string[]
    # - columnVisibility: Record<string, boolean>
    config = Column(JSONB, nullable=False)

    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="list_column_configs")

    __table_args__ = (
        Index("ix_user_list_column_configs_user_id", "user_id"),
        UniqueConstraint("user_id", "listing_key", name="uq_user_list_column_configs_user_id_listing_key"),
    )
