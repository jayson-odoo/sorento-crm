"""Sync RBAC permissions (includes system.modules.manage for App Store).

Revision ID: 097_app_store_perm
Revises: 096_app_modules_runtime
Create Date: 2026-03-20

Idempotent: inserts any missing slugs from PERMISSION_REGISTRY (e.g. system.modules.manage).
"""
from alembic import op
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "097_app_store_perm"
down_revision = "096_app_modules_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    # Do not remove permissions on downgrade (would break role assignments)
    pass
