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
    invited_by_user_id = Column(String, nullable=True)
    is_protected = Column(Boolean, default=False, nullable=False)
    respond_user_id = Column(String, nullable=True)
    respond_synced = Column(String, default="pending", nullable=False)
    superior_id = Column(String, ForeignKey("users.id"), nullable=True)
    tier = Column(Integer, nullable=True)  # Conversation SLA policy tier (1, 2, ...)
    daily_sla_summary_subscribed = Column(Boolean, default=True, nullable=False)
    
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

    # SMTP for notification emails (password not returned in read APIs)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(String(10), nullable=True)
    smtp_secure = Column(Boolean, default=True, nullable=False)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    smtp_from = Column(String(255), nullable=True)  # sender address or "Name <email>"

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
