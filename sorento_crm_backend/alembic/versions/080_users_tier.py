"""Add tier to users for conversation SLA policy tier.

Revision ID: 080_users_tier
Revises: 079_respond_contacts_id
Create Date: 2026-02-21

Stores which tier in the conversation SLA policy this user belongs to (integer).
"""
from alembic import op
import sqlalchemy as sa


revision = "080_users_tier"
down_revision = "079_respond_contacts_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tier", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "tier")
