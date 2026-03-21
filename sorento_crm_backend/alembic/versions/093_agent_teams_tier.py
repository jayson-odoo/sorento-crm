"""Add tier to agent_teams for explicit tier-based assignment (1=initial, 2/3=escalation).

Revision ID: 093_agent_teams_tier
Revises: 092_notification_delivery
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


revision = "093_agent_teams_tier"
down_revision = "092_notification_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_teams", sa.Column("tier", sa.Integer(), nullable=True))
    op.create_index("ix_agent_teams_tier", "agent_teams", ["tier"])
    # One team per tier per agent when tier is set
    op.create_index(
        "uq_agent_teams_agent_tier",
        "agent_teams",
        ["agent_id", "tier"],
        unique=True,
        postgresql_where=sa.text("tier IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_teams_agent_tier", table_name="agent_teams")
    op.drop_index("ix_agent_teams_tier", table_name="agent_teams")
    op.drop_column("agent_teams", "tier")
