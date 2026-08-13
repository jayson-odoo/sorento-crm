"""S13b: project demand comes from the Order Inquiry, and origin gets its own column.

> "the order inquiry is the demand because the SO is processed by the customer service
>  team ... order inquiry is only for project side. So for dealer side is exactly based on
>  the sales order."   (user, 2026-08-10)

Two changes, one rule:

1. `sales_orders.demand_origin` - stamped by the Order Inquiry feed at creation and never
   rewritten. It exists because adoption OVERWRITES `source_system`: when CS's outstanding
   extract takes ownership of an inquiry-created order, reading origin off `source_system`
   would delete that order's demand from the next run as a side effect of the handover.
   Backfilled from `source_system` here, which is safe exactly once: nothing has been
   adopted before this column exists to protect.

2. `scm.committed_v` learns the order-level half of the demand rule: a project-class order
   counts only when the inquiry created it; retail (and unclassified, which the importer
   already reports) counts straight from the book. What the filter sets aside is counted by
   `demand_source_service.set_aside_project_demand` - excluded, never silently dropped.

The body lives in `app.services.scm.demand.COMMITTED_V_SQL`, as it did when this migration shipped (frozen here since the live-import replay broke production; see 340), and the
view and the Python expression cannot be edited apart.

Revision ID: 346_scm_demand_origin_split
Revises: 345_scm_pooled_netting_toggle
"""
import sqlalchemy as sa
from alembic import op

revision = "346_scm_demand_origin_split"
down_revision = "345_scm_pooled_netting_toggle"
branch_labels = None
depends_on = None


_AS_OF_346 = """
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
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR so.demand_origin = 'scm_order_inquiry')
GROUP BY sol.product_id, sol.warehouse_id;
"""

_PREVIOUS_VIEW = """
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
    op.add_column("sales_orders", sa.Column("demand_origin", sa.String(32), nullable=True))
    # Safe exactly once: adoption flips source_system, but nothing can have been adopted
    # before the column existed, so today source_system still tells the truth about origin.
    op.execute(
        "UPDATE sales_orders SET demand_origin = 'scm_order_inquiry' "
        "WHERE source_system = 'scm_order_inquiry'"
    )
    op.execute(_AS_OF_346)


def downgrade() -> None:
    op.execute(_PREVIOUS_VIEW)
    op.drop_column("sales_orders", "demand_origin")
