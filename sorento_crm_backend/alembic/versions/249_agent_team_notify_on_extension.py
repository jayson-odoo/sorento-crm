"""agent_teams.notify_on_extension — per-tier deadline-extension notify control.

Revision ID: 249_agent_team_notify_ext
Revises: 248_coverage_created_by
Create Date: 2026-06-29

On an SLA deadline extension, every higher tier (current+1..3) whose team has this
flag set is notified. Default true: existing rows backfill to true so the grandparent
tier is reached out of the box (the old behaviour only notified tier current+1).
Admins untick per tier in the access-agent admin UI. See
docs/plans/UAC-sla-extension-notify-tiers.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "249_agent_team_notify_ext"
down_revision = "248_coverage_created_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_teams",
        sa.Column(
            "notify_on_extension",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_teams", "notify_on_extension")
