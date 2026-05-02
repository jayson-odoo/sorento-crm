"""Sync RBAC: user_management.contacts.portal_link permission.

Revision ID: 160_contact_portal_link
Revises: 159_user_submission_portal
Create Date: 2026-05-01
"""

from alembic import op
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "160_contact_portal_link"
down_revision = "159_user_submission_portal"
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
