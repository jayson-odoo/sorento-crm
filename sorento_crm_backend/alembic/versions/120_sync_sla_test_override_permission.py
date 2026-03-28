"""Sync RBAC: conversation SLA tracking test_override permission.

Revision ID: 120_sync_sla_test_override
Revises: 119_agent_team_multiple_tier_sets
Create Date: 2026-03-28
"""

from alembic import op
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "120_sync_sla_test_override"
down_revision = "119_agent_team_multiple_tier_sets"
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
