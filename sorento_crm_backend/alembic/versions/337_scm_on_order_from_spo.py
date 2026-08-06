"""Incoming supply is the SPO allocation, not the purchase order.

Revision ID: 337_scm_on_order_from_spo
Revises: 336_scm_supplier_inventory_loading_plan
Create Date: 2026-08-06

The chain is PO -> SPO -> GRN, and the business meaning of each link is different: a purchase
order is an order PLACED with a supplier, while the SPO allocation is the supplier's actual
shipment against it, allocated to a destination warehouse. Only the second one is stock on its
way in. `scm.on_order_v` was reading the first.

The live database says the same thing more bluntly than the argument does: 9 open purchase
order lines against 860 SPO allocations across 112 shipments. The plan's snapshot supply was
therefore ~0 while nearly a thousand real allocations were in flight, and every one of those
products looked short by the quantity already coming.

Why not count both, netting one against the other: `spo_allocations.po_line_id` is NULL on all
860 rows, so nothing can tell whether an SPO belongs to an open PO. Counting both would double
the supply for every shipped order. Decision (user, 6 Aug 2026): supply is SPO only. The
exposure is stated rather than hidden - an order placed but not yet shipped is NOT supply, so
between placing it and its first shipment the plan can recommend buying it again. Purchase
orders remain visible as ORDERED throughout, on their own screens.

The view keeps its name and its three columns, because `scm.net_position_v` selects from it
and every reader of the module goes through that.
"""
from alembic import op

revision = "337_scm_on_order_from_spo"
down_revision = "336_scm_supplier_inventory_loading_plan"
branch_labels = None
depends_on = None


#: Shipment states that mean the goods have landed. Anything else is still coming. Mirrors
#: `coverage_service._RECEIVED_SHIPMENT_STATUSES`, which the dated timeline already applies.
_RECEIVED_SHIPMENT_STATES = (
    "('fully_received', 'closed', 'received', 'completed', 'cancelled')"
)

ON_ORDER_FROM_SPO = f"""
CREATE OR REPLACE VIEW scm.on_order_v AS
SELECT sa.product_id,
       sa.warehouse_id,
       -- Cast: the SPO quantities are integers and the replaced view summed numeric.
       -- `CREATE OR REPLACE` refuses to change a view column's type, and every consumer
       -- of `net_position_v` already treats this as numeric.
       SUM((sa.allocated_quantity - COALESCE(sa.quantity_received, 0))::numeric) AS on_order
FROM spo_allocations sa
JOIN inbound_shipments s ON s.id = sa.inbound_shipment_id
-- Guard, not decoration. `spo_allocations_product_id_fkey` is NOT VALID, so rows predating
-- it were never checked: 7 live allocations name a product that no longer exists. The old
-- PO-based view never met them; this one does, and an orphan in a read model does not stay
-- in the read model - the analytics run reads the product universe from `net_position_v`
-- and then fails the whole run inserting a `demand_stat` for a product that is not there.
JOIN products pr ON pr.id = sa.product_id
WHERE s.shipment_status NOT IN {_RECEIVED_SHIPMENT_STATES}
  AND sa.receipt_status <> 'received'
  AND sa.allocated_quantity > COALESCE(sa.quantity_received, 0)
GROUP BY sa.product_id, sa.warehouse_id;
"""

#: The previous definition, for the downgrade. Kept verbatim from migration 311.
ON_ORDER_FROM_PO = """
CREATE OR REPLACE VIEW scm.on_order_v AS
SELECT pol.product_id, pol.warehouse_id,
       SUM(pol.qty_ordered - pol.qty_received) AS on_order
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE po.status IN ('active', 'received', 'partial', 'closed')
  AND pol.line_status = 'open'
  AND pol.qty_ordered > pol.qty_received
GROUP BY pol.product_id, pol.warehouse_id;
"""


#: The old body under its honest name. Nothing is lost by redefining `on_order_v`: the
#: quantity a supplier has been ORDERED is still a real figure, it is simply not supply, and
#: `CoverageService` reports it beside the balance (`qty_ordered_not_incoming`). One SQL
#: definition so the view and the service cannot drift on what "placed" means.
PO_ORDERED_V = """
CREATE OR REPLACE VIEW scm.po_ordered_v AS
SELECT pol.product_id, pol.warehouse_id,
       SUM(pol.qty_ordered - pol.qty_received) AS ordered
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE po.status IN ('active', 'received', 'partial', 'closed')
  AND pol.line_status = 'open'
  AND pol.qty_ordered > pol.qty_received
GROUP BY pol.product_id, pol.warehouse_id;
"""


def upgrade() -> None:
    # REPLACE, not drop-and-create: `scm.net_position_v` depends on this view, and dropping it
    # would take the net position with it. The column list is unchanged, which is what makes
    # the replace legal.
    op.execute(ON_ORDER_FROM_SPO)
    op.execute(PO_ORDERED_V)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS scm.po_ordered_v;")
    op.execute(ON_ORDER_FROM_PO)
