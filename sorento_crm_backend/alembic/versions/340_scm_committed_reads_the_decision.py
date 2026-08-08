"""`scm.committed_v` reads the purchasing decision, not just the sales-order quantity.

Migration 339 gave the line `qty_required` and `purchasing_status`. This teaches the view
that owns "committed" to read them, so the dashboard and the netting engine answer the same
question:

    GREATEST(COALESCE(qty_required, qty_ordered) - qty_delivered, 0)   where not covered

Behaviour is unchanged on today's data by construction. Every line carries either a
`qty_required` equal to its `qty_ordered` (written by the Order Inquiry feed) or NULL, and no
line is `covered` yet, so the COALESCE falls through to exactly the old expression. What
changes is what happens NEXT: once the sales-order book lands and CS calls off part of a line,
the plan reads the number CS decided rather than the number the customer ordered.

The body lives in `app.services.scm.demand.COMMITTED_V_SQL`, next to the Python expression
the engine uses, so the two cannot be edited apart.

Revision ID: 340_scm_committed_reads_the_decision
Revises: 339_scm_demand_decision_on_line
"""
from alembic import op

from app.services.scm.demand import COMMITTED_V_SQL

revision = "340_scm_committed_reads_the_decision"
down_revision = "339_scm_demand_decision_on_line"
branch_labels = None
depends_on = None


_PREVIOUS = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(sol.qty_ordered - sol.qty_delivered) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.qty_ordered > sol.qty_delivered
GROUP BY sol.product_id, sol.warehouse_id;
"""


def upgrade() -> None:
    op.execute(COMMITTED_V_SQL)


def downgrade() -> None:
    op.execute(_PREVIOUS)
