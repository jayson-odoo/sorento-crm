"""PRICING-UX-FIXES: a series can exclude an in-scope product

Revision ID: pux_0001_series_exclusion
Revises: pnl_0002_agent_slug
Create Date: 2026-11-01 00:00:00.000000

Additive and idempotent. `projects.series_products.excluded` (default false, so every existing row
keeps its meaning), and the quotation approval permission is renamed to "minimum price"
wording. An excluded row takes a product the series' brand / category scope would list
OUT of the series: it is not listed, not standard and not priced, until it is added back.
"""
from alembic import op

revision = "pux_0001_series_exclusion"
down_revision = "pnl_0002_agent_slug"
branch_labels = None
depends_on = None


OLD_PERMISSION_NAME = "Approve Below-Floor Quotations"
NEW_PERMISSION_NAME = "Approve Quotations Below Minimum Price"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.series_products "
        "ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT false"
    )
    # Owner wording (1 Nov): "minimum price" wherever users read it, the role editor included.
    # The registry sync never renames an existing row, so the rename is data.
    op.execute(
        "UPDATE user_permissions SET name = '" + NEW_PERMISSION_NAME + "' "
        "WHERE slug = 'projects.quotations.approve' AND name = '" + OLD_PERMISSION_NAME + "'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE user_permissions SET name = '" + OLD_PERMISSION_NAME + "' "
        "WHERE slug = 'projects.quotations.approve' AND name = '" + NEW_PERMISSION_NAME + "'"
    )
    op.execute("ALTER TABLE projects.series_products DROP COLUMN IF EXISTS excluded")
