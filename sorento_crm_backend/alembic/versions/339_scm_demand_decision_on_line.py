"""Carry the purchasing decision on the sales-order line.

The business runs two books over the same demand. AutoCount holds the commercial record: what
the customer ordered and what has shipped. The Order Inquiry sheet holds what CS decided about
it: which lines still need buying, how much of each to cover, and which purchase order is
carrying it.

Those are two writers, and last-writer-wins between them is how a quantity CS corrected
silently reverts to whatever a spreadsheet said last week. So each owns its own columns:

    qty_ordered, qty_delivered   <- the sales-order book
    qty_required, purchasing_status <- the Order Inquiry sheet

`qty_required` is NULLABLE on purpose. NULL is not zero and it is not "same as ordered": it
means nobody has ruled on this line, so netting falls back to `qty_ordered - qty_delivered`
and an amendment on the sales-order side flows straight through. Once CS states a number the
line keeps it until CS states another.

`purchasing_status` defaults to `not_reviewed`, which COUNTS as demand. A line nobody has got
to yet must not quietly vanish from the plan.

Revision ID: 339_scm_demand_decision_on_line
Revises: 338_scm_autocount_so_detail_aliases
"""
from alembic import op
import sqlalchemy as sa

revision = "339_scm_demand_decision_on_line"
down_revision = "338_scm_autocount_so_detail_aliases"
branch_labels = None
depends_on = None

_TABLE = "sales_order_lines"


def _columns(bind) -> set[str]:
    return {
        c["name"] for c in sa.inspect(bind).get_columns(_TABLE)
    }


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)

    if "qty_required" not in existing:
        op.add_column(_TABLE, sa.Column("qty_required", sa.Numeric(15, 4), nullable=True))
    if "purchasing_status" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "purchasing_status",
                sa.String(24),
                nullable=False,
                server_default="not_reviewed",
            ),
        )
        # Partial: the plan only ever asks this of open lines, and the closed ones are the
        # overwhelming majority (64,526 absorbed history rows against 15,481 open).
        op.create_index(
            "ix_sales_order_lines_purchasing_status",
            _TABLE,
            ["purchasing_status"],
            postgresql_where=sa.text("line_status = 'open'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    if "purchasing_status" in existing:
        op.drop_index("ix_sales_order_lines_purchasing_status", table_name=_TABLE)
        op.drop_column(_TABLE, "purchasing_status")
    if "qty_required" in existing:
        op.drop_column(_TABLE, "qty_required")
