"""Feature icons: each spec value carries its own ordered Dealer Kit icons.

PRICETAG-DESIGNER-GAPS item 3, owner ruling 5 Nov 20:35: the icon <-> spec link lives on the
spec VALUE. `product_spec_registry.value_icons` is `{value: [asset id, ...]}`, staff-owned and
never seed-repaired, like `value_labels`. Additive only.

(This revision replaces the unmerged `dkfi_0001_asset_show_when`, which put the rule on the
asset. A database that ran that one keeps its two unused `dealer_kit.asset.show_when_*`
columns; nothing reads them and nothing is dropped here.)

Revision ID: dkfi_0001_spec_value_icons
Revises: ttdc_0001_tag_template_archived
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "dkfi_0001_spec_value_icons"
down_revision = "ttdc_0001_tag_template_archived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "ALTER TABLE product_spec_registry "
            "ADD COLUMN IF NOT EXISTS value_icons JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS value_icons")
    )
