"""User management models."""
import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
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
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=True)
    country = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    name = Column(String, nullable=True)
    role_id = Column(UUID(as_uuid=False), ForeignKey("user_roles.id"), nullable=False)
    status = Column(String, default=UserStatus.INACTIVE.value, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_sign_in_at = Column(DateTime(timezone=True), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    is_trashed = Column(Boolean, default=False, nullable=False)
    avatar = Column(String, nullable=True)
    invited_by_user_id = Column(UUID(as_uuid=False), nullable=True)
    is_protected = Column(Boolean, default=False, nullable=False)
    
    role = relationship("UserRole", back_populates="users")
    system_logs = relationship("SystemLog", back_populates="user")
    
    __table_args__ = (
        Index("users_invited_by_user_id_idx", "invited_by_user_id"),
        Index("users_role_id_idx", "role_id"),
        Index("users_status_idx", "status"),
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_trashed = Column(Boolean, default=False, nullable=False)
    created_by_user_id = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_protected = Column(Boolean, default=False, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    users = relationship("User", back_populates="role")
    permissions = relationship("UserRolePermission", back_populates="role")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    roles = relationship("UserRolePermission", back_populates="permission")


class UserRolePermission(Base):
    __tablename__ = "user_role_permissions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(UUID(as_uuid=False), ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=False), ForeignKey("user_permissions.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    role = relationship("UserRole", back_populates="permissions")
    permission = relationship("UserPermission", back_populates="roles")
    
    __table_args__ = (
        Index("user_role_permissions_role_id_permission_id_key", "role_id", "permission_id", unique=True),
    )


class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
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
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, default="My Company", nullable=False)
    logo = Column(String, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    address = Column(Text, nullable=True)
    website_url = Column(String, nullable=True)
    support_email = Column(String, nullable=True)
    support_phone = Column(String, nullable=True)
    language = Column(String, default="en", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    currency = Column(String, default="USD", nullable=False)
    currency_format = Column(String, default="$ {value}", nullable=False)
    
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
