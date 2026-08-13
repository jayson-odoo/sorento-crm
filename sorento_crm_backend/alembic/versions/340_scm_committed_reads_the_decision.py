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

The body below is FROZEN as it stood when this migration shipped. It used to import the
live `COMMITTED_V_SQL`, and that import is exactly how the first from-zero replay of this
chain died in production: S13b later added a `demand_origin` clause to the live SQL, so
replaying THIS migration emitted a reference to a column only migration 346 adds. A
migration describes a point in history; only the newest view migration may match the live
body, and `tests/scm/test_committed_v_migration_chain.py` pins both facts.

Revision ID: 340_scm_committed_reads_the_decision
Revises: 339_scm_demand_decision_on_line
"""
from alembic import op

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


_AS_OF_340 = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                    - COALESCE(sol.qty_delivered, 0), 0)) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.purchasing_status <> 'covered'
  AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
               - COALESCE(sol.qty_delivered, 0), 0) > 0
GROUP BY sol.product_id, sol.warehouse_id;
"""


def upgrade() -> None:
    op.execute(_AS_OF_340)


def downgrade() -> None:
    op.execute(_PREVIOUS)
