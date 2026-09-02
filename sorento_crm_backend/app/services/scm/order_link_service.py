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

The purchase side is one of TWO tables, decided by the number the claim carries. A
`######-S####` number names a `purchase_order_lines` row; an `SPO-####/##-####` number names
a `spo_allocations` row, because since migration 420 that is where a shipping order lives.
The claim records whichever it found in the matching column and is resolved either way - a
claim that could only ever look in `purchase_order_lines` would have left 12,393 pairings
permanently unresolvable the day the SPO documents moved.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import nullslast, or_
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services.scm.po_listing_reader import FAMILY_SPO, doc_family
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _dec(value) -> Decimal:
    """A quantity as a Decimal, treating an absent one as nothing."""
    return Decimal(str(value)) if value is not None else _ZERO


#: Which column a resolved purchase side lands in. The reader returns the pair so the two
#: families share one lookup and one loop, rather than a second copy of both.
_PO_SIDE = "po_line_id"
_SPO_SIDE = "spo_allocation_id"


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

        if claim.po_line_id is None and claim.spo_allocation_id is None:
            found = (
                po_line_by_key.get((claim.po_number, claim.item_code))
                if claim.item_code
                else po_line_by_number.get(claim.po_number)
            )
            if found is not None:
                column, row_id = found
                setattr(claim, column, str(row_id))
                po_side += 1

        if claim.so_line_id and (claim.po_line_id or claim.spo_allocation_id):
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


def _purchase_side_of(claim: OrderLinkClaim) -> Optional[str]:
    """Whichever of the two columns this claim's purchase side landed in, or None.

    One reading, because "is this claim still waiting for its purchase document" is asked in
    more than one place and an answer that only looks at `po_line_id` calls every resolved
    SPO claim unresolved.
    """
    return claim.po_line_id or claim.spo_allocation_id


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
    """Where each document number resolves to, as `(column, id)`.

    Two tables, one lookup. The family is read from the number's PREFIX - the same authority
    the import channels route on, and the only one that cannot disagree with itself - so a
    claim never has to be asked which table it meant.

    Ordering is explicit on the SPO side: one shipping order can state the same product on
    several lines (two containers), so the lowest line number wins rather than whichever row
    the database happened to return first.
    """
    spo_numbers = {n for n in po_numbers if doc_family(n) == FAMILY_SPO}
    po_only = po_numbers - spo_numbers

    rows = (
        db.query(PurchaseOrder.po_number, Product.product_code, PurchaseOrderLine.id)
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .join(Product, Product.id == PurchaseOrderLine.product_id)
        .filter(PurchaseOrder.po_number.in_(list(po_only)))
        .all()
        if po_only
        else []
    )
    by_key: dict[tuple[str, str], tuple[str, str]] = {
        (str(po), str(code)): (_PO_SIDE, str(line_id)) for po, code, line_id in rows
    }
    by_number: dict[str, tuple[str, str]] = {}
    for po, _code, line_id in rows:
        by_number.setdefault(str(po), (_PO_SIDE, str(line_id)))

    spo_rows = (
        db.query(SPOAllocation.spo_number, Product.product_code, SPOAllocation.id)
        .join(Product, Product.id == SPOAllocation.product_id)
        .filter(SPOAllocation.spo_number.in_(list(spo_numbers)))
        .order_by(
            SPOAllocation.spo_number,
            Product.product_code,
            nullslast(SPOAllocation.spo_line_number.asc()),
            SPOAllocation.id,
        )
        .all()
        if spo_numbers
        else []
    )
    for number, code, allocation_id in spo_rows:
        by_key.setdefault((str(number), str(code)), (_SPO_SIDE, str(allocation_id)))
        by_number.setdefault(str(number), (_SPO_SIDE, str(allocation_id)))
    return by_key, by_number


#: The claim a SUPPLY WRITER makes for a line it has just created for known demand -
#: G12's write-time rule (captain, 2 Sep 2026). Held apart from `order_inquiry`, which is
#: the audit echo of a link, because two readers turn on the difference: the netting in
#: `project_order_inquiry_service._reserved_for_netting` (an `order_inquiry` claim's
#: quantity is already counted by its own link) and the one-shot repair that drops the
#: withdrawn born-claimed mechanism's artifacts without touching a real attribution.
SOURCE_CRM_SUPPLY = "crm_supply"

#: The book's own `FromSODocList` column, read by the OUTSTANDING purchase channel. The
#: history channel writes `po_history` for the same fact off the same column; the two are
#: kept apart so an upload result can say which book stated the pairing.
SOURCE_PO_UPLOAD = "po_upload"

#: The audit row `ProjectOrderInquiryService._write_link` writes beside every placement.
SOURCE_ORDER_INQUIRY = "order_inquiry"


def find_claim(
    db: Session,
    *,
    company_id: Optional[str],
    so_number: str,
    po_number: str,
    item_code: Optional[str],
) -> Optional[OrderLinkClaim]:
    """The claim at this identity, or None - ONE spelling of the lookup every writer needs.

    The identity is the database's own unique index, `uq_scm_order_link_claim_identity`:
    the company, the two document numbers, and the item code coalesced. Scoped to the SAME
    company the row would be stamped with, because the index is per company (migration 335)
    and the system principal reads across every company while writing into the incumbent
    one - without the filter another company's claim would suppress a claim this one is
    missing.
    """
    query = db.query(OrderLinkClaim).filter(
        OrderLinkClaim.so_number == so_number,
        OrderLinkClaim.po_number == po_number,
        OrderLinkClaim.item_code.is_(None)
        if item_code is None
        else OrderLinkClaim.item_code == item_code,
    )
    if company_id is not None:
        query = query.filter(OrderLinkClaim.company_id == company_id)
    return query.first()


def claim_book_pairing(
    db: Session,
    *,
    company_id: Optional[str],
    so_number: str,
    po_number: str,
    item_code: Optional[str],
    source: str,
    now: Optional[datetime] = None,
    po_line_id: Optional[str] = None,
    spo_allocation_id: Optional[str] = None,
) -> OrderLinkClaim:
    """Get-or-create a claim a FEED states, leaving resolution to `resolve()`.

    The difference from `claim_placed_on_po` below is what the caller knows. A placement
    knows both ends - it is holding the purchase line and the sales line - so it records
    the pairing RESOLVED. A book states a pairing and nothing else: the sales order it
    names may not have been uploaded yet, which is the whole reason this table is claims
    rather than a nullable foreign key. So the row goes in open and `resolve()` fills in
    each side as it appears, exactly as the purchase-history channel has always relied on.

    An existing claim is refreshed rather than doubled, and its `source` is LEFT ALONE:
    the first feed to state a pairing is the one that knows it, and a later channel
    restating the same fact is not evidence the provenance changed.
    """
    existing = find_claim(
        db,
        company_id=company_id,
        so_number=so_number,
        po_number=po_number,
        item_code=item_code,
    )
    if existing is not None:
        if po_line_id and existing.po_line_id is None:
            existing.po_line_id = po_line_id
        if spo_allocation_id and existing.spo_allocation_id is None:
            existing.spo_allocation_id = spo_allocation_id
        return existing
    claim = OrderLinkClaim(
        company_id=company_id,
        so_number=so_number,
        po_number=po_number,
        item_code=item_code,
        source=source,
        claimed_at=now or _now(),
        po_line_id=po_line_id,
        spo_allocation_id=spo_allocation_id,
    )
    db.add(claim)
    return claim


def reservations_by_target(
    db: Session, *, target_ids: Optional[Sequence[str]] = None
) -> dict[str, list[dict]]:
    """What every RESOLVED claim reserves, keyed by the PO line or SPO allocation it names.

    G7 (`PLAN-scm-reorder-oi-feedback-1sep.md` S6): a claim carries no quantity of its own,
    it reserves the claiming sales order LINE's LIVE outstanding - so a fulfilled or
    cancelled line reserves nothing, whatever the claim still names, and the claim row is
    never deleted to make that true. Joined rather than stored for exactly that reason.

    `so_number` is read off the CLAIM's OWN column, never `SalesOrder.so_number` off the
    join: the write side (`ProjectOrderInquiryService.claim_identity`) stores
    `ProjectSalesOrder.autocount_doc_no or provisional_ref`, which is not always the
    reconciled core number this join can also reach, and comparing the two identities made
    a row's own claim unrecognisable as its own.

    ONE reader, two consumers - the cascade's dedication netting
    (`ProjectOrderInquiryService._claims_by_target`, whole table, cached per instance) and
    the purchase order's "Allocated to" panel (`PurchaseOrderService._allocations_for`,
    narrowed to one document's lines). A second spelling of "what does this claim reserve"
    is how a panel and the walk behind it come to print different numbers for the same line.
    """
    query = (
        db.query(
            OrderLinkClaim.id,
            OrderLinkClaim.po_line_id,
            OrderLinkClaim.spo_allocation_id,
            OrderLinkClaim.so_number,
            OrderLinkClaim.source,
            SalesOrder.order_date,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
            SalesOrderLine.line_status,
        )
        .join(SalesOrderLine, SalesOrderLine.id == OrderLinkClaim.so_line_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
    )
    if target_ids is None:
        query = query.filter(
            or_(
                OrderLinkClaim.po_line_id.isnot(None),
                OrderLinkClaim.spo_allocation_id.isnot(None),
            )
        )
    else:
        wanted = [str(t) for t in target_ids]
        if not wanted:
            return {}
        query = query.filter(
            or_(
                OrderLinkClaim.po_line_id.in_(wanted),
                OrderLinkClaim.spo_allocation_id.in_(wanted),
            )
        )
    out: dict[str, list[dict]] = {}
    for (
        claim_id,
        po_line_id,
        spo_allocation_id,
        so_number,
        source,
        order_date,
        qty_ordered,
        qty_delivered,
        line_status,
    ) in query.all():
        key = str(po_line_id or spo_allocation_id)
        outstanding = (
            _ZERO
            if (line_status or "open") != "open"
            else max(_dec(qty_ordered) - _dec(qty_delivered), _ZERO)
        )
        out.setdefault(key, []).append(
            {
                "claim_id": str(claim_id),
                "so_number": so_number,
                "source": source,
                "so_date": order_date,
                "outstanding": outstanding,
            }
        )
    for claims in out.values():
        # SO-date order, the order G7 says claims reserve in, with the id as the tie-break
        # so two orders of the same date read the same way twice.
        claims.sort(
            key=lambda c: (c["so_date"] is None, c["so_date"] or date.max, c["claim_id"])
        )
    return out


def claim_placed_on_po(
    db: Session,
    *,
    company_id: Optional[str],
    so_number: str,
    po_number: str,
    item_code: Optional[str],
    so_line_id: Optional[str],
    po_line_id: Optional[str] = None,
    spo_allocation_id: Optional[str] = None,
    source: str = SOURCE_ORDER_INQUIRY,
) -> OrderLinkClaim:
    """Record a Link PO / Link SPO pairing as a claim, for the audit trail
    (PLAN-demo-followups-19aug-ladder-v2.md section G, PLAN-scm-cs-planning-uat.md 3.I).

    `source` is what the caller is: `order_inquiry` (the default) for the audit row written
    beside a link, `crm_supply` for a supply writer claiming a line it has just created for
    known demand (G12's write-time rule). It applies to a claim this call CREATES; a claim
    that already exists keeps the source of whoever stated the pairing first.

    The purchase side is whichever column the caller resolved: `po_line_id` for a purchase
    order line, `spo_allocation_id` for a shipping order, which since migration 420 is a
    row in `spo_allocations`. Exactly one is passed, the same rule the resolver applies to
    a claim it fills in itself and the same rule the link row's own CHECK constraint holds.

    Reuses the SAME identity `resolve()` matches on - (company, so_number, po_number,
    item_code coalesced), which is also the database's own unique index
    (`uq_scm_order_link_claim_identity`). A pairing another feed already knows (the PO
    history import already noted "SO:xxx" on this same PO, say) is resolved onto the
    existing row rather than doubled: inserting a duplicate would fail the unique index
    anyway, and the existing claim is the more honest record either way.
    """
    now = _now()
    existing = find_claim(
        db,
        company_id=company_id,
        so_number=so_number,
        po_number=po_number,
        item_code=item_code,
    )
    if existing is not None:
        if existing.so_line_id is None:
            existing.so_line_id = so_line_id
        existing.po_line_id = po_line_id
        existing.spo_allocation_id = spo_allocation_id
        existing.resolved_at = now
        return existing

    claim = OrderLinkClaim(
        company_id=company_id,
        so_number=so_number,
        po_number=po_number,
        item_code=item_code,
        source=source,
        claimed_at=now,
        so_line_id=so_line_id,
        po_line_id=po_line_id,
        spo_allocation_id=spo_allocation_id,
        resolved_at=now,
    )
    db.add(claim)
    db.flush()
    return claim


def delete_own_claim(
    db: Session,
    *,
    company_id: Optional[str],
    so_number: str,
    po_number: str,
    item_code: Optional[str],
) -> None:
    """Remove the audit claim "Place on PO" wrote, on Untag.

    Scoped to `source = 'order_inquiry'` on purpose: a claim at this same identity that
    another feed (PO history, an upload) is the source of was not this row's to make, and
    untagging must not take somebody else's evidence down with it.
    """
    query = db.query(OrderLinkClaim).filter(
        OrderLinkClaim.so_number == so_number,
        OrderLinkClaim.po_number == po_number,
        OrderLinkClaim.item_code.is_(None)
        if item_code is None
        else OrderLinkClaim.item_code == item_code,
        OrderLinkClaim.source == "order_inquiry",
    )
    if company_id is not None:
        query = query.filter(OrderLinkClaim.company_id == company_id)
    claim = query.first()
    if claim is not None:
        db.delete(claim)


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
        "waiting_for_purchase_order": sum(1 for c in rows if _purchase_side_of(c) is None),
        "sales_orders": sorted({c.so_number for c in rows if c.so_line_id is None})[:200],
        "purchase_orders": sorted(
            {c.po_number for c in rows if _purchase_side_of(c) is None}
        )[:200],
    }
