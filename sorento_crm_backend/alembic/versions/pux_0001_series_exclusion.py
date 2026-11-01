"""PRICING-UX-FIXES: a series can exclude an in-scope product

Revision ID: pux_0001_series_exclusion
Revises: oisn_0002_full_table
Create Date: 2026-11-01 00:00:00.000000

Additive and idempotent. `projects.series_products.excluded` (default false, so every existing row
keeps its meaning). An excluded row takes a product the series' brand / category scope would list
OUT of the series: it is not listed, not standard and not priced, until it is added back.
"""
from alembic import op

revision = "pux_0001_series_exclusion"
down_revision = "oisn_0002_full_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.series_products "
        "ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.series_products DROP COLUMN IF EXISTS excluded")
