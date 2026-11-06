"""TAG-TEMPLATE-DELETE-CONFIRM: `dealer_kit.tag_template.archived_at`.

Deleting a tag template now archives it (stamps this column) instead of removing the row, so its
versions, its product/combo links and the request lines that print with it all survive and the
template can be restored (`archived_at = NULL`). Additive and nullable.

Revision ID: ttdc_0001_tag_template_archived
Revises: pol_0001_stock_debt_link_po
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ttdc_0001_tag_template_archived"
down_revision = "pol_0001_stock_debt_link_po"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "ALTER TABLE dealer_kit.tag_template "
            "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITHOUT TIME ZONE"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("ALTER TABLE dealer_kit.tag_template DROP COLUMN IF EXISTS archived_at")
    )
