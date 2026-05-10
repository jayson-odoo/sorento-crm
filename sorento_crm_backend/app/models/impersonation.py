"""Impersonation session model.

Tracks an admin actively browsing as another user. Permission checks use the
target user's grants; audit / created_by / updated_by remain the real admin.
"""
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.database import Base


class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=False), nullable=True)
    started_ip = Column(String(100), nullable=True)
    started_user_agent = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_impersonation_sessions_admin_user_id", "admin_user_id"),
        Index("ix_impersonation_sessions_target_user_id", "target_user_id"),
        Index(
            "uq_impersonation_sessions_active_admin",
            "admin_user_id",
            unique=True,
            postgresql_where="ended_at IS NULL",
        ),
    )
