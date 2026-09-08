"""`purchase_order_lines` and `spo_allocations` gain `from_so_external`
(V5, ingest-contract-2-2-so-links).

The cross-book case of a sales-order line reference: the sales order lives
in ANOTHER AutoCount database, so its key never resolves into a Sorento id.
Recorded raw, verbatim from the payload's `from_so_external` object - the
smallest honest place for a fact that never becomes a row we can join to.
Not `scm.order_link_claim`: that table's identity requires a real
`so_number`, which a cross-book key does not carry, and reusing it would
mean either inventing a fake number or making `so_number` nullable for
every other caller of that table.

Both nullable, no backfill, no default.

Revision ID: 494_from_so_external_link
Revises: 493_spo_alloc_from_po_link
"""
import sqlalchemy as sa
from alembic import op

revision = "494_from_so_external_link"
down_revision = "493_spo_alloc_from_po_link"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS from_so_external JSONB"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS from_so_external JSONB"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_so_external"))
    bind.execute(
        sa.text("ALTER TABLE purchase_order_lines DROP COLUMN IF EXISTS from_so_external")
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
