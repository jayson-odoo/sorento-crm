"""`scm.order_summary_row` gains `last_receipt_spo_number` / `last_receipt_container_number`
(PLAN-low-stock-last-in-and-list-scope S1).

The "Last in" cell moves from reading GR picking lines (where `qty_accepted` is NULL on
every row measured) to the newest VISIBLE `spo_allocations` line per product, received or
not (owner ruling, second round) - see `app.services.spo_last_receipt_service.last_in_map`.
The sheet also needs to name which SPO and container that line came from, so this
migration adds two nullable text columns beside the existing `last_receipt_date` /
`last_receipt_qty`.

R4 (no backfill): a frozen row from before this migration keeps NULL in both new columns
forever - the chat tool always creates a fresh run, and the buyer re-runs the plan for the
on-screen sheet, so there is no frozen population worth reconstructing.

Revision ID: 518_osr_last_receipt_spo
Revises: ptag_0009_combos_tags

The plan named `517_chatbot_low_stock_vocab` as the down_revision (that was origin/main's
head when the plan was written); by the time this lane branched, `ptag_0009_combos_tags`
had merged on top of it, so this re-parents onto the actual current head (lane merge
discipline, `./scripts/alembic-reparent.sh`) rather than creating a second head.
"""
import sqlalchemy as sa
from alembic import op

revision = "518_osr_last_receipt_spo"
down_revision = "ptag_0009_combos_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_summary_row",
        sa.Column("last_receipt_spo_number", sa.String(length=100), nullable=True),
        schema="scm",
    )
    op.add_column(
        "order_summary_row",
        sa.Column("last_receipt_container_number", sa.String(length=100), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("order_summary_row", "last_receipt_container_number", schema="scm")
    op.drop_column("order_summary_row", "last_receipt_spo_number", schema="scm")
