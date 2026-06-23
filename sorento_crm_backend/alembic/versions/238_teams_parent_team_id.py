"""add teams.parent_team_id self-FK for team hierarchy

Revision ID: 238_teams_parent
Revises: c1d2e3f4a5b6
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = "238_teams_parent"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("parent_team_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_teams_parent_team_id",
        "teams",
        "teams",
        ["parent_team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_teams_parent_team_id", "teams", ["parent_team_id"])


def downgrade() -> None:
    op.drop_index("ix_teams_parent_team_id", table_name="teams")
    op.drop_constraint("fk_teams_parent_team_id", "teams", type_="foreignkey")
    op.drop_column("teams", "parent_team_id")
