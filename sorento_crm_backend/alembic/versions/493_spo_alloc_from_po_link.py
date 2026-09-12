"""`purchase_order_lines` and `spo_allocations` both gain the AutoCount
linkage widen columns (V5, ingest-contract-2-2-so-links; widened B2 review
fix - originally `spo_allocations` only).

B2 (review ruling): every field the wire sends is persisted uniformly on
BOTH line tables, not on `spo_allocations` alone - `from_so_line_ref` in
particular is the whole point of this slice, and a purchase order pushed
before its sales order must not lose the exact ref forever (it is what
`order_link_service._exact_so_line_for` re-reads on a later `resolve()`
sweep). `from_po_line_ref` / `from_po_number` are raw pass-through - never
resolved into an id - what lets an order-inquiry row that reserved against
an SPO print the purchase order the buyer actually reads; `spo_allocations`
already carried these two before the widen. All nullable, no backfill, no
default: every pre-existing row simply states nothing.

Revision ID: 493_spo_alloc_from_po_link
Revises: ptag_0005
"""
import sqlalchemy as sa
from alembic import op

revision = "493_spo_alloc_from_po_link"
down_revision = "ptag_0005"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS from_po_line_ref VARCHAR(255)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS from_po_number VARCHAR(100)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS from_so_line_ref VARCHAR(255)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS from_so_line_ref VARCHAR(255)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS from_po_line_ref VARCHAR(255)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS from_po_number VARCHAR(100)"
        )
    )


def revert(bind) -> None:
    bind.execute(
        sa.text("ALTER TABLE purchase_order_lines DROP COLUMN IF EXISTS from_po_number")
    )
    bind.execute(
        sa.text("ALTER TABLE purchase_order_lines DROP COLUMN IF EXISTS from_po_line_ref")
    )
    bind.execute(
        sa.text("ALTER TABLE purchase_order_lines DROP COLUMN IF EXISTS from_so_line_ref")
    )
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_so_line_ref"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_po_number"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_po_line_ref"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
