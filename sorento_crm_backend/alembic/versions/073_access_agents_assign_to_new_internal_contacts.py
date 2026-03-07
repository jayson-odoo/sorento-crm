"""Add assign_to_new_internal_contacts to access_agents.

Revision ID: 073_assign_new_contacts
Revises: 072_seed_scheduled_tasks
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "073_assign_new_contacts"
down_revision = "072_seed_scheduled_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "access_agents",
        sa.Column("assign_to_new_internal_contacts", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_access_agents_assign_to_new_internal_contacts",
        "access_agents",
        ["assign_to_new_internal_contacts"],
    )


def downgrade() -> None:
    op.drop_index("ix_access_agents_assign_to_new_internal_contacts", table_name="access_agents")
    op.drop_column("access_agents", "assign_to_new_internal_contacts")
