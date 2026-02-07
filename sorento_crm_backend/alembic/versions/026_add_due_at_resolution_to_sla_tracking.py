"""Add due_at_resolution to conversation_sla_tracking.

Revision ID: 026_due_at_resolution
Revises: 025_add_resolution_hours
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "026_due_at_resolution"
down_revision = "025_add_resolution_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("due_at_resolution", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_sla_tracking", "due_at_resolution")
