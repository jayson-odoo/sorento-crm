"""Sync RBAC permissions, including system.ai_assistant_* slugs.

Revision ID: 145_ai_assistant_permissions_sync
Revises: 144_ai_assistant_core
"""

from alembic import op
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "145_ai_assistant_permissions_sync"
down_revision = "144_ai_assistant_core"
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
    pass
