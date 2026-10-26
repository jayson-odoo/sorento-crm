"""Where a placement's goods are now: one answer for every screen (LINKAGE-UNIFY).

`PLAN-linkage-unify-26oct.md` sections 4 and 7. A placement (`order_inquiry_links` row) names
ONE document line and nothing ever repoints it: a PO line AutoCount transferred onto a shipping
order keeps its links on the PO (F1), and the PO line's `qty_received` is that transfer, not a
receipt (F2). Every reader asking "where are this SO line's goods" has to bridge PO -> SPO
itself, and four readers bridged it four ways (plan section 1, SO364824 line 880).

**This is Stock Debt's split, lifted out unchanged** (SUPPLY-SPO-LINK, #1850; SPO-RECEIVED-PIN,
#1388), so the next reader asks it instead of restating it:

* a placement on a PO line takes what each SPO the line was transferred onto can still hold
  (`follow_capacity`, earliest expected first): an `in_transit` hop while the SPO is incoming,
  a `received` hop at the SPO's bin for what it landed once it is not. What is left is held on
  the PO only for what the line still has on order (`on_order`);
* a placement on an SPO line is `in_transit` for its whole quantity while the line is
  incoming (not capped: `assign()` caps), and `received` for what the line landed once it is
  not.

**Screen-independent.** Each PO line and each transferred allocation is a pool the placements
share in the order they were made (`linked_at, id`), over EVERY live placement on the PO line,
whatever the caller asked for. Asking for one placement or for the whole book gives that
placement the same hops.

Out on purpose: whether the goods are still in the bin (Stock Debt's `found_empty` and the
`assign()` floors), ETA wording, and the book-text S/O pins. The chain says where the goods
were received, not what the bin holds now.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_, tuple_
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryLink, OrderInquiryRow
from app.services.company_scope import build_company_predicate
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import spo_supply
from app.services.scm.supply_assignment import EPSILON

#: Hop states (plan section 4). U1 produces the first three; U2 produces the last two.
ON_ORDER = "on_order"
IN_TRANSIT = "in_transit"
RECEIVED = "received"
RECEIVED_DIRECT = "received_direct"
DEAD = "dead"

KIND_PO = "po"
KIND_SPO = "spo"

_ZERO = Decimal("0")
_EPSILON = Decimal(str(EPSILON))


@dataclass(frozen=True)
class Hop:
    """One leg of where a placement's quantity is: on a PO line (`kind` `po`) or on an SPO
    allocation (`kind` `spo`). `warehouse_*` is set on a `received` hop only, the bin the
    goods were received at."""

    kind: str
    state: str
    qty: Decimal
    po_line_id: Optional[str] = None
    po_number: Optional[str] = None
    purchase_order_id: Optional[str] = None
    spo_allocation_id: Optional[str] = None
    spo_number: Optional[str] = None
    spo_line_number: Optional[int] = None
    warehouse_id: Optional[str] = None
    warehouse_code: Optional[str] = None
    #: U2: `po_cancelled` | `spo_withdrawn` on a `dead` hop.
    reason: Optional[str] = None


@dataclass(frozen=True)
class LinkChain:
    """One placement and its hops, in the order the split hands the quantity out."""

    link_id: str
    row_id: str
    placed_qty: Decimal
    hops: Tuple[Hop, ...]

    @property
    def unplaced_qty(self) -> Decimal:
        """What no hop holds: a placement past what its documents can carry."""
        return self.placed_qty - sum((hop.qty for hop in self.hops), _ZERO)


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def landed_qty(
    allocated: float, received: float, *, arrived: bool, receipt_status: Optional[str]
) -> float:
    """What an SPO line that is NO LONGER incoming brought into its bin (SPO-RECEIVED-PIN).

    The receipt when the book has written one; the whole allocation when only the
    shipment's arrival, or the line's own receipt status, says the goods are in; nothing for
    a line closed with nothing received and nothing landed - that document brought no stock
    anywhere, so a placement on it holds no stock either.
    """
    if received > EPSILON:
        return received
    if arrived or receipt_status in spo_supply.RECEIVED_RECEIPT_STATUSES:
        return allocated
    return 0.0


def follow_capacity(spo: Any) -> float:
    """SUPPLY-SPO-LINK: what an SPO allocation a PO line was transferred onto can hold of
    the placements that follow that line (the PO walk in `chains_for_links`): the whole
    allocation while it is still incoming, only what it landed once it is not. A line closed
    with nothing landed holds nothing, so the placement falls through to the PO's own
    on-order quantity instead of vanishing."""
    allocated = _float(spo.spo_allocated)
    received = _float(spo.spo_received)
    if bool(spo.spo_incoming) and allocated > received:
        return allocated
    return landed_qty(
        allocated,
        received,
        arrived=spo.spo_arrived is not None,
        receipt_status=spo.spo_receipt_status,
    )


def transferred_allocations(
    db: Session, po_lines: Sequence[Any]
) -> Dict[Tuple[str, str, str], List[Any]]:
    """SUPPLY-SPO-LINK: by `(po_number, trimmed source_ref, product_id)`, the SPO
    allocations each PO line in `po_lines` was transferred onto - OI-SPO-EXACT, the key
    `project_order_inquiry_service._append_derived_spo_entries` resolves a PO link's SPOs
    by - earliest arrival first. One read for every line. `po_lines` rows carry
    `po_number`, `po_line_ref` (trimmed) and `po_product_id`.

    Every visible allocation, not only the open ones: a landed allocation is where the
    goods ARE, and the split turns it into a `received` hop. A PO line with no `source_ref`
    reaches nothing. The company predicate is stated by hand, as the OI reader states it:
    the join is on plain text off the AutoCount feed.
    """
    keys = {
        (row.po_number, row.po_line_ref, str(row.po_product_id))
        for row in po_lines
        if row.po_number and row.po_line_ref and row.po_product_id
    }
    if not keys:
        return {}
    company_predicate = build_company_predicate(SPOAllocation, get_company_scope(db))
    rows = (
        db.query(
            SPOAllocation.from_po_number,
            func.btrim(SPOAllocation.from_po_line_ref).label("from_ref"),
            SPOAllocation.id.label("spo_allocation_id"),
            SPOAllocation.spo_number,
            SPOAllocation.spo_line_number,
            and_(*spo_supply.open_incoming_clauses()).label("spo_incoming"),
            SPOAllocation.allocated_quantity.label("spo_allocated"),
            SPOAllocation.quantity_received.label("spo_received"),
            SPOAllocation.receipt_status.label("spo_receipt_status"),
            SPOAllocation.product_id.label("spo_product_id"),
            SPOAllocation.warehouse_id.label("spo_warehouse_id"),
            Warehouse.warehouse_code.label("spo_warehouse_code"),
            InboundShipment.actual_arrival_date.label("spo_arrived"),
        )
        .outerjoin(
            InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
        )
        .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .filter(
            tuple_(
                SPOAllocation.from_po_number,
                func.btrim(SPOAllocation.from_po_line_ref),
                SPOAllocation.product_id,
            ).in_(sorted(keys)),
            *spo_supply.visible_line_clauses(),
            *((company_predicate,) if company_predicate is not None else ()),
        )
        .order_by(
            SPOAllocation.expected_date.asc().nullslast(),
            SPOAllocation.spo_number,
            SPOAllocation.spo_line_number,
            SPOAllocation.id,
        )
        .all()
    )
    out: Dict[Tuple[str, str, str], List[Any]] = {}
    for row in rows:
        out.setdefault(
            (row.from_po_number, row.from_ref, str(row.spo_product_id)), []
        ).append(row)
    return out


def chains_for_links(db: Session, link_ids: Iterable[str]) -> Dict[str, LinkChain]:
    """By link id, the chain of each live placement in `link_ids`. A link on a cancelled
    order inquiry row, or a reserve link (no document line), is absent."""
    ids = sorted({str(link_id) for link_id in link_ids if link_id})
    if not ids:
        return {}
    return _chains(db, _placements(db, OrderInquiryLink.id.in_(ids)))


def chains_for_rows(db: Session, row_ids: Iterable[str]) -> Dict[str, List[LinkChain]]:
    """By order inquiry row id, the chains of the row's live placements in `linked_at, id`
    order. A row with none (cancelled, or nothing placed) is absent."""
    ids = sorted({str(row_id) for row_id in row_ids if row_id})
    if not ids:
        return {}
    wanted = _placements(db, OrderInquiryLink.row_id.in_(ids))
    chains = _chains(db, wanted)
    out: Dict[str, List[LinkChain]] = {}
    for row in wanted:
        out.setdefault(str(row.row_id), []).append(chains[str(row.link_id)])
    return out


def _placements(db: Session, *criteria: Any) -> List[Any]:
    """The live placements matching `criteria`, made-first first, each with the columns of
    the document line it names. Live: the order inquiry row is not cancelled and the link
    names a PO or SPO line. A retired SPO line with nothing received stays in the read, so
    its placement still answers (with no hop); `spo_visible` says which it is."""
    return (
        db.query(
            OrderInquiryLink.id.label("link_id"),
            OrderInquiryLink.row_id,
            OrderInquiryLink.qty,
            OrderInquiryLink.spo_allocation_id,
            OrderInquiryLink.po_line_id,
            SPOAllocation.spo_number,
            SPOAllocation.spo_line_number,
            and_(*spo_supply.visible_line_clauses()).label("spo_visible"),
            # The shared incoming rule, evaluated in SQL on the row itself; the quantity
            # half is applied in `_spo_hop`, beside the arithmetic. NULL-safe for a PO link.
            and_(*spo_supply.open_incoming_clauses()).label("spo_incoming"),
            SPOAllocation.allocated_quantity.label("spo_allocated"),
            SPOAllocation.quantity_received.label("spo_received"),
            SPOAllocation.receipt_status.label("spo_receipt_status"),
            SPOAllocation.warehouse_id.label("spo_warehouse_id"),
            Warehouse.warehouse_code.label("spo_warehouse_code"),
            InboundShipment.actual_arrival_date.label("spo_arrived"),
            # Is the placed PO line still on order (`_po_rows`'s own test), and what did it
            # transfer? NULL for an SPO link, whose branch never reads them.
            and_(*ProjectSupplyService.open_po_line_clauses()).label("po_open"),
            PurchaseOrderLine.qty_ordered.label("po_ordered"),
            PurchaseOrderLine.qty_received.label("po_received"),
            func.btrim(PurchaseOrderLine.source_ref).label("po_line_ref"),
            PurchaseOrderLine.product_id.label("po_product_id"),
            PurchaseOrder.po_number,
            PurchaseOrder.id.label("purchase_order_id"),
        )
        .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
        .outerjoin(SPOAllocation, SPOAllocation.id == OrderInquiryLink.spo_allocation_id)
        .outerjoin(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
        .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .outerjoin(PurchaseOrderLine, PurchaseOrderLine.id == OrderInquiryLink.po_line_id)
        .outerjoin(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            # A cancelled inquiry row holds nothing, as every other reader of these links.
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            or_(
                OrderInquiryLink.po_line_id.isnot(None),
                OrderInquiryLink.spo_allocation_id.isnot(None),
            ),
            *criteria,
        )
        .order_by(OrderInquiryLink.linked_at, OrderInquiryLink.id)
        .all()
    )


def _chains(db: Session, wanted: Sequence[Any]) -> Dict[str, LinkChain]:
    """The chain of each placement in `wanted` (rows of `_placements`)."""
    po_line_ids = sorted(
        {str(row.po_line_id) for row in wanted if not row.spo_allocation_id and row.po_line_id}
    )
    po_hops: Dict[str, List[Hop]] = {}
    if po_line_ids:
        # Every live placement on each touched PO line, not only the ones asked for: they
        # share the line's documents, so the split must see them all to be the same split.
        po_hops = _po_split(
            db, _placements(db, OrderInquiryLink.po_line_id.in_(po_line_ids))
        )
    out: Dict[str, LinkChain] = {}
    for row in wanted:
        placed = _dec(row.qty)
        hops: List[Hop] = []
        if not row.spo_allocation_id:
            hops = po_hops.get(str(row.link_id), [])
        elif row.spo_visible and placed > 0:
            # A retired SPO line with nothing received is not shown anywhere: no hop (U2
            # makes it a `dead` one).
            hop = _spo_hop(row, placed)
            if hop is not None:
                hops = [hop]
        out[str(row.link_id)] = LinkChain(
            link_id=str(row.link_id),
            row_id=str(row.row_id),
            placed_qty=placed,
            hops=tuple(hops),
        )
    return out


def _po_split(db: Session, placements: Sequence[Any]) -> Dict[str, List[Hop]]:
    """By link id, the hops of each placement on a PO line (SUPPLY-SPO-LINK). `placements`
    is every live placement on the lines, made-first first: each transferred allocation and
    each line's on-order rest is a pool they share in that order, so two placements never
    claim the same units. Whatever is neither transferred nor on order (a short-closed line)
    gets no hop."""
    transferred_to = transferred_allocations(db, placements)
    po_left: Dict[str, Decimal] = {
        str(row.po_line_id): (
            max(_dec(row.po_ordered) - _dec(row.po_received), _ZERO) if row.po_open else _ZERO
        )
        for row in placements
    }
    spo_left: Dict[str, Decimal] = {
        str(spo.spo_allocation_id): _dec(follow_capacity(spo))
        for spos in transferred_to.values()
        for spo in spos
    }
    out: Dict[str, List[Hop]] = {}
    for row in placements:
        hops: List[Hop] = []
        out[str(row.link_id)] = hops
        rest = _dec(row.qty)
        if rest <= 0:
            continue
        for spo in transferred_to.get(
            (row.po_number, row.po_line_ref, str(row.po_product_id)), ()
        ):
            key = str(spo.spo_allocation_id)
            take = min(rest, spo_left[key])
            if take <= _EPSILON:
                continue
            spo_left[key] -= take
            rest -= take
            hop = _spo_hop(spo, take)
            if hop is not None:
                hops.append(hop)
            if rest <= _EPSILON:
                break
        take = min(rest, po_left[str(row.po_line_id)])
        if take <= _EPSILON:
            continue
        po_left[str(row.po_line_id)] -= take
        hops.append(
            Hop(
                kind=KIND_PO,
                state=ON_ORDER,
                qty=take,
                po_line_id=str(row.po_line_id),
                po_number=row.po_number,
                purchase_order_id=str(row.purchase_order_id)
                if row.purchase_order_id
                else None,
            )
        )
    return out


def _spo_hop(spo: Any, qty: Decimal) -> Optional[Hop]:
    """`qty` of a placement on one SPO allocation (`spo`, a row carrying the `spo_*`
    columns): `in_transit` while the line is incoming, else `received` for what it landed
    (SPO-RECEIVED-PIN), at its bin. None when it landed nothing."""
    allocated = _float(spo.spo_allocated)
    received = _float(spo.spo_received)
    if bool(spo.spo_incoming) and allocated > received:
        return Hop(
            kind=KIND_SPO,
            state=IN_TRANSIT,
            qty=qty,
            spo_allocation_id=str(spo.spo_allocation_id),
            spo_number=spo.spo_number,
            spo_line_number=spo.spo_line_number,
        )
    landed = landed_qty(
        allocated,
        received,
        arrived=spo.spo_arrived is not None,
        receipt_status=spo.spo_receipt_status,
    )
    take = min(qty, _dec(landed))
    if take <= _EPSILON:
        return None
    return Hop(
        kind=KIND_SPO,
        state=RECEIVED,
        qty=take,
        spo_allocation_id=str(spo.spo_allocation_id),
        spo_number=spo.spo_number,
        spo_line_number=spo.spo_line_number,
        warehouse_id=str(spo.spo_warehouse_id) if spo.spo_warehouse_id else None,
        warehouse_code=spo.spo_warehouse_code,
    )
