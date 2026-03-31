"""Add user subscription flag for daily SLA summary.

Revision ID: 125_user_daily_sla_summary_subscription
Revises: 124_user_sla_daily_summary
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa


revision = "125_user_daily_sla_summary_subscription"
down_revision = "124_user_sla_daily_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "daily_sla_summary_subscribed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET daily_sla_summary_subscribed = true "
            "WHERE daily_sla_summary_subscribed IS NULL"
        )
    )
    op.alter_column("users", "daily_sla_summary_subscribed", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "daily_sla_summary_subscribed")
