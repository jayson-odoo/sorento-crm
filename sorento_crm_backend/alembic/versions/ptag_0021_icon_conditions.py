"""Registry: conditions on a value's icon (an AND over other spec values).

SPEC-ICON-COMBINED (plan documentation/plans/dealer-kit/PLAN-spec-icon-combined-09nov.md):
`product_spec_registry.value_icon_conditions JSONB NOT NULL DEFAULT '{}'`, shaped
`{value: {icon_id: [{spec_key, value}]}}`. Idempotent (`IF NOT EXISTS`), additive only.

Revision ID: ptag_0021_icon_conditions
Revises: ptag_0020_variant_excl
"""
from __future__ import annotations

from alembic import op

revision = "ptag_0021_icon_conditions"
down_revision = "ptag_0020_variant_excl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE product_spec_registry "
        "ADD COLUMN IF NOT EXISTS value_icon_conditions JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS value_icon_conditions")
