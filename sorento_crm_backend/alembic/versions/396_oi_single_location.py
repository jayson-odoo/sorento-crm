"""order_inquiry_rows.stock_location - one row names one location.

`ProjectSupplyService._restamp_stock_location` used to join every reserve/borrow
component's warehouse code onto the confirmed ORDER row (`" + "`-separated), and
`ProjectOrderInquiryService._stock_location` did the same for the amendment path with
`" / "`. The ORDER row is the buy handed to purchasing; its destination is the line's
OWN fulfilment location - a joined string is not a real place, and it can never match a
borrow-shortfall row netted by `(item_code, stock_location)`. Both call sites were fixed
in the same change; this backfills the rows already written the old way.

Resolution: for a row whose `so_line_id` reconciles to a CORE `sales_order_lines` line
with a warehouse, use that warehouse's code (mirrors `_LineFacts.own_code`, what the
fixed code now writes going forward). Where that join finds nothing - no `so_line_id`,
no reconciled core line, or no warehouse on it - fall back to the text before the first
separator, which is still the line's OWN location in every joined string either call
site ever wrote (`own_code` was always listed first).

Idempotent: both passes are scoped to rows still containing `" + "` or `" / "`, and a
real `warehouse_code` never contains either substring, so a re-run matches nothing.

Revision ID: 396_oi_single_location
Revises: 395_so_line_uom
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "396_oi_single_location"
down_revision = "395_so_line_uom"
branch_labels = None
depends_on = None


def _has_table(bind, table: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT to_regclass(:qualified)"
            ),
            {"qualified": f"{schema}.{table}"},
        ).scalar()
    )


def apply(bind) -> int:
    """Collapse every joined `stock_location` on `order_inquiry_rows` to one code.

    Returns the number of rows changed.
    """
    if not _has_table(bind, "order_inquiry_rows", schema="projects"):
        return 0

    resolved = bind.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_rows AS oir
               SET stock_location = w.warehouse_code
              FROM projects.sales_order_lines AS psl
              JOIN sales_order_lines AS sol ON sol.id = psl.core_sales_order_line_id
              JOIN warehouses AS w ON w.id = sol.warehouse_id
             WHERE oir.so_line_id = psl.id
               AND (oir.stock_location LIKE '% + %' OR oir.stock_location LIKE '% / %')
               AND oir.stock_location IS DISTINCT FROM w.warehouse_code
            """
        )
    ).rowcount or 0

    # Whatever the join above could not resolve (no so_line_id, no reconciled core
    # line, or the core line carries no warehouse): the text before the first
    # separator, which both old call sites always wrote `own_code` into first.
    unresolved = bind.execute(
        sa.text(
            r"""
            UPDATE projects.order_inquiry_rows
               SET stock_location = regexp_replace(stock_location, '\s*[+/]\s*.*$', '')
             WHERE stock_location LIKE '% + %' OR stock_location LIKE '% / %'
            """
        )
    ).rowcount or 0

    return resolved + unresolved


def revert(bind) -> int:
    """No-op. Which components made up the old joined string is not recorded anywhere
    once collapsed - the composition lives on the confirmed decision's snapshots, not
    on this column - so there is nothing to restore. Rows changed: always 0.
    """
    return 0


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
