"""Add resolution_hours to SLA policy tiers.

Revision ID: 025_add_resolution_hours
Revises: 024_add_access_controls
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "025_add_resolution_hours"
down_revision = "024_add_access_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "sla_policy_tiers" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("sla_policy_tiers")]
        if "resolution_hours" not in columns:
            op.add_column(
                "sla_policy_tiers",
                sa.Column("resolution_hours", sa.Integer(), nullable=False, server_default="24"),
            )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "sla_policy_tiers" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("sla_policy_tiers")]
        if "resolution_hours" in columns:
            op.drop_column("sla_policy_tiers", "resolution_hours")
