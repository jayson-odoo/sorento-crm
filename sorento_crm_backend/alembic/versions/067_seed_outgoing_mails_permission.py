"""Seed RBAC permission for outgoing mails log.

Revision ID: 067_outgoing_mails_perm
Revises: 066_requested_approval_by
Create Date: 2026-02-21

"""

from alembic import op
from sqlalchemy.orm import Session
from app.rbac.permission_registry import sync_permissions


revision = "067_outgoing_mails_perm"
down_revision = "066_requested_approval_by"
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

