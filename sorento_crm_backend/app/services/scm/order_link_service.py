"""L4 - resolving the SO<->PO linkage, whichever file arrived first.

> "if I upload PO before SO, then the SO doesn't exist and the linkage is not formed, which
> means I need to store the SO number first so that when I upload SO later, it can identify
> the linkage from PO and build the linkage so this is both-way compatible"

That is exactly what this does, and the reason the pairing is a claim rather than a nullable
foreign key: a claim made before the other document exists still has somewhere to live.

The resolver is **idempotent and order-independent**. It runs after every upload - purchase
history, order inquiry, the SO book, the PO book - and fills in whichever side is now
present. Running it twice changes nothing; running it before either side exists changes
nothing and loses nothing.

Matching is on **(SO number, item code)** where the claim states an item, which is the
identity the Order Inquiry sheet itself keys on. Claims from the PO notes state no item, so
they resolve at document level: they link the ORDER, and pin the purchase-order side only.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def resolve(db: Session, *, so_numbers: Optional[set[str]] = None) -> dict:
    """Fill in whichever side of each open claim now exists.

    `so_numbers` narrows the work to the documents an upload just touched; omitted, every
    open claim is retried, which is what a periodic sweep or a backfill wants.

    A claim is RESOLVED only when both sides are found. One side alone is still progress -
    the id is recorded - but the pairing is not a pairing until both ends exist, and marking
    it resolved early would hide the half that is still missing.
    """
    query = db.query(OrderLinkClaim).filter(OrderLinkClaim.resolved_at.is_(None))
    if so_numbers:
        query = query.filter(OrderLinkClaim.so_number.in_(list(so_numbers)))
    claims = query.all()
    if not claims:
        return {"examined": 0, "resolved": 0, "so_side": 0, "po_side": 0, "still_open": 0}

    so_line_by_key, so_line_by_number = _sales_side(db, {c.so_number for c in claims})
    po_line_by_key, po_line_by_number = _purchase_side(db, {c.po_number for c in claims})

    resolved = so_side = po_side = 0
    now = _now()

    for claim in claims:
        if claim.so_line_id is None:
            # A claim with an item resolves to THAT line; one without (a PO note) can only
            # name the order, so it takes the order's first line as its anchor and stays
            # honest about the fact by having no item code.
            line = (
                so_line_by_key.get((claim.so_number, claim.item_code))
                if claim.item_code
                else so_line_by_number.get(claim.so_number)
            )
            if line is not None:
                claim.so_line_id = str(line.id)
                so_side += 1

        if claim.po_line_id is None:
            line = (
                po_line_by_key.get((claim.po_number, claim.item_code))
                if claim.item_code
                else po_line_by_number.get(claim.po_number)
            )
            if line is not None:
                claim.po_line_id = str(line.id)
                po_side += 1

        if claim.so_line_id and claim.po_line_id:
            claim.resolved_at = now
            resolved += 1

    db.flush()
    return {
        "examined": len(claims),
        "resolved": resolved,
        "so_side": so_side,
        "po_side": po_side,
        "still_open": sum(1 for c in claims if c.resolved_at is None),
    }


def _sales_side(db: Session, so_numbers: set[str]):
    rows = (
        db.query(SalesOrder.so_number, Product.product_code, SalesOrderLine)
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .filter(SalesOrder.so_number.in_(list(so_numbers)))
        .all()
        if so_numbers
        else []
    )
    by_key = {(str(so), str(code)): line for so, code, line in rows}
    by_number: dict[str, SalesOrderLine] = {}
    for so, _code, line in rows:
        by_number.setdefault(str(so), line)
    return by_key, by_number


def _purchase_side(db: Session, po_numbers: set[str]):
    rows = (
        db.query(PurchaseOrder.po_number, Product.product_code, PurchaseOrderLine)
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .join(Product, Product.id == PurchaseOrderLine.product_id)
        .filter(PurchaseOrder.po_number.in_(list(po_numbers)))
        .all()
        if po_numbers
        else []
    )
    by_key = {(str(po), str(code)): line for po, code, line in rows}
    by_number: dict[str, PurchaseOrderLine] = {}
    for po, _code, line in rows:
        by_number.setdefault(str(po), line)
    return by_key, by_number


def open_claims(db: Session) -> dict:
    """What is still waiting, and for which side.

    Reported on the upload result rather than kept as a silence: "34 sales orders name a
    purchase order we have not seen" is how somebody finds out the PO book is a month behind,
    and there is no other way to find it out.
    """
    rows = db.query(OrderLinkClaim).filter(OrderLinkClaim.resolved_at.is_(None)).all()
    return {
        "open": len(rows),
        "waiting_for_sales_order": sum(1 for c in rows if c.so_line_id is None),
        "waiting_for_purchase_order": sum(1 for c in rows if c.po_line_id is None),
        "sales_orders": sorted({c.so_number for c in rows if c.so_line_id is None})[:200],
        "purchase_orders": sorted({c.po_number for c in rows if c.po_line_id is None})[:200],
    }
