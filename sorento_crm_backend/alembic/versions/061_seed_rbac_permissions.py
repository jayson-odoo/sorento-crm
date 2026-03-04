"""Seed RBAC permissions from permission registry.

Revision ID: 061_seed_rbac_permissions
Revises: 060_user_role_assignments
Create Date: 2026-02-21

"""
from alembic import op
from sqlalchemy.orm import Session
from app.rbac.permission_registry import sync_permissions


revision = "061_seed_rbac_permissions"
down_revision = "060_user_role_assignments"
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
