"""Sync RBAC permissions for complaint approve/reject actions.

Adds ``complaint_management.complaints.approve`` and ``.reject`` to
``user_permissions`` via the central ``sync_permissions`` helper. Idempotent  - 
safe to re-run; existing slugs are left alone.

Revision ID: 171_seed_complaint_decision_rbac
Revises: 170_respond_inbox_url_use_respond_io_id
Create Date: 2026-05-05
"""

from alembic import op


revision = "171_seed_complaint_decision_rbac"
down_revision = "170_respond_inbox_url_use_respond_io_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.orm import Session

    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session)
    finally:
        session.close()


def downgrade() -> None:
    # Permission rows are intentionally left in place on downgrade so
    # role/user grants pointing at them don't dangle. Re-running upgrade is
    # idempotent.
    pass
