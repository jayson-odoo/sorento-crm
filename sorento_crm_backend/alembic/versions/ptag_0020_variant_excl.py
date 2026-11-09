"""Price tag request line: the variant members unticked for a family tag.

PRICETAG-UPGRADE-VARIANTS S3 (plan documentation/plans/dealer-kit/PLAN-pricetag-upgrade-variants-09nov.md):
`price_tag_request_lines.excluded_variant_ids JSONB NOT NULL DEFAULT '[]'`. The line stores the UNTICKED
members, so a variant created later joins the tag ticked. Idempotent (`IF NOT EXISTS`), additive only.

Revision ID: ptag_0020_variant_excl
Revises: lpcui_0001_list_price_changed
"""
from __future__ import annotations

from alembic import op

revision = "ptag_0020_variant_excl"
down_revision = "lpcui_0001_list_price_changed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE price_tag_request_lines "
        "ADD COLUMN IF NOT EXISTS excluded_variant_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS excluded_variant_ids")
