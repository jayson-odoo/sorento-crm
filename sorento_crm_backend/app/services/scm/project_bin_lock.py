"""G12's own count: OPEN project-bin PO/SPO lines nobody has claimed at all
(`PLAN-scm-reorder-oi-feedback-1sep.md` S6, AC-6.11).

Company-wide and always current, never scoped to one upload's own rows: a re-export's
`FromSODocList` notes can resolve a claim onto a line an EARLIER upload wrote, so what
matters to Joey is what remains unclaimed after this pass runs, not what this pass alone
touched. Surfaced on the PO/SPO upload result and as a PO-view filter, so the backfill
has a number to chase to zero rather than a silent gap.

"Claimed" here means named by a `scm.order_link_claim` at all - resolved or not. An
UNRESOLVED claim (the SO side not yet uploaded) still says somebody typed a reference for
this line; it is the ABSENCE of any claim that leaves G12's lock with nothing to open
except a manual link.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, PurchaseOrderLine, SPOAllocation
from app.models.scm import OrderLinkClaim
from app.services.scm import spo_supply
from app.services.scm.pool_predicate import PROJECT_SEGMENT


def count_unclaimed_project_bin_lines(
    db: Session, company_id: Optional[str] = None
) -> int:
    """Every OPEN PO line or SPO allocation at a `segment = 'project'` warehouse that
    no claim names - the number G12's lock refuses to the automatic cascade until a
    claim exists, whether Joey's next re-export writes one or a buyer links it by hand.
    """
    po_query = (
        db.query(PurchaseOrderLine.id)
        .join(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
        .outerjoin(OrderLinkClaim, OrderLinkClaim.po_line_id == PurchaseOrderLine.id)
        .filter(
            PurchaseOrderLine.line_status == "open",
            Warehouse.segment == PROJECT_SEGMENT,
            OrderLinkClaim.id.is_(None),
        )
    )
    spo_query = (
        db.query(SPOAllocation.id)
        .join(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .outerjoin(
            InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
        )
        .outerjoin(
            OrderLinkClaim, OrderLinkClaim.spo_allocation_id == SPOAllocation.id
        )
        .filter(
            *spo_supply.open_incoming_clauses(),
            Warehouse.segment == PROJECT_SEGMENT,
            OrderLinkClaim.id.is_(None),
        )
    )
    if company_id:
        po_query = po_query.filter(PurchaseOrderLine.company_id == company_id)
        spo_query = spo_query.filter(SPOAllocation.company_id == company_id)
    return po_query.count() + spo_query.count()


def has_unclaimed_project_bin_line(db: Session):
    """The PO-view filter's EXISTS clause (AC-6.11): does THIS purchase order carry at
    least one open line this same rule counts - the same predicate `count_unclaimed_
    project_bin_lines` sums company-wide, correlated instead to one `PurchaseOrder` row
    so `purchase_order_service.list` can filter on it the same way `allocated` already
    does.
    """
    from app.models.procurement import PurchaseOrder

    return (
        db.query(PurchaseOrderLine.id)
        .join(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
        .outerjoin(OrderLinkClaim, OrderLinkClaim.po_line_id == PurchaseOrderLine.id)
        .filter(
            PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
            PurchaseOrderLine.line_status == "open",
            Warehouse.segment == PROJECT_SEGMENT,
            OrderLinkClaim.id.is_(None),
        )
        .exists()
    )
