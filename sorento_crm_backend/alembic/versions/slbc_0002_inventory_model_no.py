"""scm.supplier_inventory.model_no - the 型号 exactly as the supplier wrote it

Revision ID: slbc_0002_inventory_model_no
Revises: lbrt_0001_local_buy_toggle
Create Date: 2026-09-19 00:00:00.000000

Owner feedback round 5 on `PLAN-stock-list-bare-model-codes.md`: "Supplier says" (the
Supplier codes tab) showed the translated words but never the sheet's own 型号 - `item_code`
can be OUR composed guess for a bare model (`SRTWC8613-250`), and the picker has to lead
with what the supplier actually printed.

This column was first added by editing `ifa_supplier_word_col.py` in place, before
realising PR #1000 (that migration) had already merged and deployed to prod - a migration
already applied there must never be edited again, so the column is re-cut here as its own
migration instead. `ADD COLUMN IF NOT EXISTS`: two local databases picked up the column
from that abandoned in-place edit before it was reverted, so a plain `ADD COLUMN` would
fail with a duplicate-column error on them.
"""
from alembic import op

revision = "slbc_0002_inventory_model_no"
down_revision = "lbrt_0001_local_buy_toggle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm.supplier_inventory ADD COLUMN IF NOT EXISTS model_no VARCHAR(120)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm.supplier_inventory DROP COLUMN IF EXISTS model_no")
