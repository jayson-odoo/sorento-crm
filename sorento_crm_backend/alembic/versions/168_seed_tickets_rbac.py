"""Sync RBAC permissions for the new ``tickets`` module.

Calls the central ``sync_permissions`` helper after the registry has been
extended with ticket slugs (``tickets.tickets.{view,add,edit,delete,view_all,
assign,export}``). Idempotent — safe to re-run.

Revision ID: 168_seed_tickets_rbac
Revises: 167_create_tickets_module
Create Date: 2026-05-03
"""

from alembic import op


revision = "168_seed_tickets_rbac"
down_revision = "167_create_tickets_module"
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
