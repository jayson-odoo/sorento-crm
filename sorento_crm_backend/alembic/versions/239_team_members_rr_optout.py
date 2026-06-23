"""add team_members.include_in_round_robin (per-team RR opt-out)

Revision ID: 239_tm_rr_optout
Revises: 238_teams_parent
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = "239_tm_rr_optout"
down_revision = "238_teams_parent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_members",
        sa.Column(
            "include_in_round_robin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Backfill existing rows to eligible (server_default already covers new rows).
    op.execute("UPDATE team_members SET include_in_round_robin = true")


def downgrade() -> None:
    op.drop_column("team_members", "include_in_round_robin")
