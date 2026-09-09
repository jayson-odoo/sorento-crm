"""Index `sales_orders.source_ref` for the book linkage resolver (review of PR #764, F3).

`order_link_service.book_so_numbers_by_ref` filters `sales_orders.source_ref IN (...)` on
every PO detail read (and now every order-inquiry PO lightbox read) to turn the AutoCount
book's own SO linkage into a printable number. Unindexed, `EXPLAIN` on the local copy
showed a sequential scan over `sales_orders` (87,292 rows) for that filter.

Partial, matching `SalesOrder.__table_args__`: `source_ref` is null on every sales order
that did not arrive through the book, which is most rows on an older order book, and a
full index over mostly-null values buys nothing a partial one does not already give.

Revision ID: 495_sales_orders_source_ref_idx
Revises: 494_from_so_external_link
"""
import sqlalchemy as sa
from alembic import op

revision = "495_sales_orders_source_ref_idx"
down_revision = "494_from_so_external_link"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_sales_orders_source_ref "
            "ON sales_orders (source_ref) WHERE source_ref IS NOT NULL"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_sales_orders_source_ref"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
