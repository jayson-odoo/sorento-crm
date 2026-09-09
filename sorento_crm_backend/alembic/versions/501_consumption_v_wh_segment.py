"""`scm.consumption_v` gains `warehouse_segment` (S7, PLAN-reorder-feedback-9sep.md, G1
ruling 9 Sep 2026).

"Retail deliveries = delivery-order lines shipped from a `dealer`-segment warehouse. A
line shipped from a `project` bin (BRW-IB, BRW-BB, ...) is a project delivery." The
AutoCount level suggestion (`reorder_level_service.average_daily_usage`,
`monthly_movement`) reads this column to filter to retail-only deliveries; health
(`movement_class`) is unchanged and keeps reading every delivery.

`CREATE OR REPLACE VIEW`, appending the column at the end - Postgres allows a view
replacement to ADD a trailing column but not to reorder, retype or remove an existing one,
so every other column here is byte-for-byte the original definition
(`274_scm_m0_views_reg.py`). Additive: no existing reader of this view is affected.

Revision ID: 501_consumption_v_wh_segment
Revises: 500_product_exclude_planning
"""
import sqlalchemy as sa
from alembic import op

revision = "501_consumption_v_wh_segment"
down_revision = "500_product_exclude_planning"
branch_labels = None
depends_on = None

_NEW_VIEW = """
CREATE OR REPLACE VIEW scm.consumption_v AS
SELECT ol.product_id, ol.warehouse_id, o.order_date::date AS day,
       SUM(ol.quantity) AS qty_out, ms.demand_nature,
       w.segment AS warehouse_segment
FROM order_lines ol
JOIN orders o ON o.id = ol.order_id
LEFT JOIN customers c ON c.id = o.customer_id
LEFT JOIN market_segments ms ON ms.code = c.market_segment_code
LEFT JOIN warehouses w ON w.id = ol.warehouse_id
WHERE o.is_cancelled = false
GROUP BY ol.product_id, ol.warehouse_id, o.order_date::date, ms.demand_nature, w.segment;
"""

_OLD_VIEW = """
CREATE OR REPLACE VIEW scm.consumption_v AS
SELECT ol.product_id, ol.warehouse_id, o.order_date::date AS day,
       SUM(ol.quantity) AS qty_out, ms.demand_nature
FROM order_lines ol
JOIN orders o ON o.id = ol.order_id
LEFT JOIN customers c ON c.id = o.customer_id
LEFT JOIN market_segments ms ON ms.code = c.market_segment_code
WHERE o.is_cancelled = false
GROUP BY ol.product_id, ol.warehouse_id, o.order_date::date, ms.demand_nature;
"""


def apply(bind) -> None:
    bind.execute(sa.text(_NEW_VIEW))


def revert(bind) -> None:
    bind.execute(sa.text(_OLD_VIEW))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
