"""`scm.net_position_v` gains a PO-only key (AC-3, `PLAN-po-spo-site-pool-and-order-
sheet-downloads.md`, slice S1).

The view's `keys` CTE was `stock UNION on_order_v UNION committed_v` (migration 376) - a
warehouse holding ONLY an open PO line (no stock row, no SPO, no committed SO) never became
an `np` row at all, so its PO was silently absent from `_planning_rows` regardless of the
site-pool gate landing in the same slice. `scm.po_ordered_v` (migration 337) joins the union
so that warehouse gets a key; `po_ordered_v`'s own LEFT JOIN two lines down already reads it,
so no other clause in the view moves.

`CREATE OR REPLACE VIEW` only - the column list is unchanged (an extra UNION arm inside one
CTE, not a new output column), so no CASCADE drop is needed and every consumer of
`scm.net_position_v` keeps reading the exact same shape.

Revision ID: 512_net_position_po_ordered
Revises: 511_supplier_country_id
"""
from alembic import op

revision = "512_net_position_po_ordered"
down_revision = "511_supplier_country_id"
branch_labels = None
depends_on = None


#: As of migration 376 (unchanged since), for the downgrade.
_AS_OF_376 = """
CREATE OR REPLACE VIEW scm.net_position_v AS
WITH keys AS (
    SELECT product_id, warehouse_id FROM stock
    UNION
    SELECT product_id, warehouse_id FROM scm.on_order_v
    UNION
    SELECT product_id, warehouse_id FROM scm.committed_v
)
SELECT k.product_id, k.warehouse_id,
       COALESCE(s.quantity_on_hand, 0) AS quantity_on_hand,
       COALESCE(oo.on_order, 0) AS on_order,
       COALESCE(cm.committed, 0) AS committed,
       COALESCE(s.quantity_on_hand, 0) + COALESCE(oo.on_order, 0)
         - COALESCE(cm.committed, 0) AS net_position
FROM keys k
LEFT JOIN stock s ON s.product_id = k.product_id AND s.warehouse_id = k.warehouse_id
LEFT JOIN scm.on_order_v oo
  ON oo.product_id = k.product_id AND oo.warehouse_id = k.warehouse_id
LEFT JOIN scm.committed_v cm
  ON cm.product_id = k.product_id AND cm.warehouse_id = k.warehouse_id;
"""

#: `po_ordered_v` added to the `keys` UNION so a PO-only warehouse gets a row.
_AS_OF_512 = """
CREATE OR REPLACE VIEW scm.net_position_v AS
WITH keys AS (
    SELECT product_id, warehouse_id FROM stock
    UNION
    SELECT product_id, warehouse_id FROM scm.on_order_v
    UNION
    SELECT product_id, warehouse_id FROM scm.committed_v
    UNION
    SELECT product_id, warehouse_id FROM scm.po_ordered_v
)
SELECT k.product_id, k.warehouse_id,
       COALESCE(s.quantity_on_hand, 0) AS quantity_on_hand,
       COALESCE(oo.on_order, 0) AS on_order,
       COALESCE(cm.committed, 0) AS committed,
       COALESCE(s.quantity_on_hand, 0) + COALESCE(oo.on_order, 0)
         - COALESCE(cm.committed, 0) AS net_position
FROM keys k
LEFT JOIN stock s ON s.product_id = k.product_id AND s.warehouse_id = k.warehouse_id
LEFT JOIN scm.on_order_v oo
  ON oo.product_id = k.product_id AND oo.warehouse_id = k.warehouse_id
LEFT JOIN scm.committed_v cm
  ON cm.product_id = k.product_id AND cm.warehouse_id = k.warehouse_id;
"""


def upgrade() -> None:
    op.execute(_AS_OF_512)


def downgrade() -> None:
    op.execute(_AS_OF_376)
