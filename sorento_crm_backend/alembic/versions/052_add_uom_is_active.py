"""Add is_active to units_of_measure

Revision ID: 052_uom_is_active
Revises: 051_fix_negative_prices
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa


revision = "052_uom_is_active"
down_revision = "051_fix_negative_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "units_of_measure",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_units_of_measure_is_active",
        "units_of_measure",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_units_of_measure_is_active", table_name="units_of_measure")
    op.drop_column("units_of_measure", "is_active")
