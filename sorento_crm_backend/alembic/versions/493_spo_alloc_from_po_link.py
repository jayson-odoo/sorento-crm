"""`spo_allocations` gains the source purchase-order link the AutoCount
linkage widen carries (V5, ingest-contract-2-2-so-links).

`from_po_line_ref` / `from_po_number` are raw pass-through - never resolved
into an id - what lets an order-inquiry row that reserved against this SPO
print the purchase order the buyer actually reads. Both nullable, no
backfill, no default: every pre-existing row simply states nothing.

Revision ID: 493_spo_alloc_from_po_link
Revises: 492_mcp_tool_chatbot_domain
"""
import sqlalchemy as sa
from alembic import op

revision = "493_spo_alloc_from_po_link"
down_revision = "492_mcp_tool_chatbot_domain"
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


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_po_number"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS from_po_line_ref"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
