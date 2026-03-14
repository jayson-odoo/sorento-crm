"""Sync RBAC permissions from registry (e.g. stock inquiry workflow, numbering).

Adds any permission from permission_registry that is not yet in user_permissions,
so they appear in the role edit dialog and can be assigned to roles.

Revision ID: 090_sync_rbac
Revises: 089_order_lines
Create Date: 2026-03-14

"""
from alembic import op
from sqlalchemy.orm import Session
from app.rbac.permission_registry import sync_permissions


revision = "090_sync_rbac"
down_revision = "089_order_lines"
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
