"""Feature icons: a "show when" rule on a Dealer Kit icon asset.

PRICETAG-DESIGNER-GAPS item 3 (documentation/plans/dealer-kit/pricetag-feature-icons-contract.md
B1). An icon asset carries ``show_when_spec_key`` + ``show_when_values``: it shows on a tag's
Feature icons layer when the product's spec has one of those raw values. Both or neither.

Revision ID: dkfi_0001_asset_show_when
Revises: ttdc_0001_tag_template_archived
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "dkfi_0001_asset_show_when"
down_revision = "ttdc_0001_tag_template_archived"
branch_labels = None
depends_on = None

_CHECK = "ck_dealer_kit_asset_show_when_pair"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE dealer_kit.asset ADD COLUMN IF NOT EXISTS show_when_spec_key VARCHAR(64)"
        )
    )
    bind.execute(
        sa.text("ALTER TABLE dealer_kit.asset ADD COLUMN IF NOT EXISTS show_when_values TEXT[]")
    )
    bind.execute(sa.text(f"ALTER TABLE dealer_kit.asset DROP CONSTRAINT IF EXISTS {_CHECK}"))
    bind.execute(
        sa.text(
            f"ALTER TABLE dealer_kit.asset ADD CONSTRAINT {_CHECK} "
            "CHECK ((show_when_spec_key IS NULL) = (show_when_values IS NULL))"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(f"ALTER TABLE dealer_kit.asset DROP CONSTRAINT IF EXISTS {_CHECK}"))
    bind.execute(sa.text("ALTER TABLE dealer_kit.asset DROP COLUMN IF EXISTS show_when_values"))
    bind.execute(sa.text("ALTER TABLE dealer_kit.asset DROP COLUMN IF EXISTS show_when_spec_key"))
