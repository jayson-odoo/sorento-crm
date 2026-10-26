"""Where a placement's goods are now: one answer for every screen (LINKAGE-UNIFY).

`PLAN-linkage-unify-26oct.md` sections 4, 7 and 8. A placement (`order_inquiry_links` row)
names ONE document line and nothing ever repoints it: a PO line AutoCount transferred onto a
shipping order keeps its links on the PO (F1), and the PO line's `qty_received` is that
transfer, not a receipt (F2). Every reader asking "where are this SO line's goods" has to bridge
PO -> SPO itself, and four readers bridged it four ways (plan section 1, SO364824 line 880).

**The logic is Stock Debt's split, lifted out of `StockDebtService._holds`** (SUPPLY-SPO-LINK,
#1850; SPO-RECEIVED-PIN, #1388), so the next reader asks it instead of restating it. One thing
changed in the lift (U1, below): the split now counts every live placement on the PO line.

* a placement on a PO line takes what each SPO the line was transferred onto can still hold
  (`follow_capacity`, earliest expected first): an `in_transit` hop while the SPO is incoming,
  a `received` hop at the SPO's bin for what it landed once it is not. What is left is held on
  the PO only for what the line still has on order (`on_order`);
* a placement on an SPO line is `in_transit` for its whole quantity while the line is
  incoming (not capped: `assign()` caps), and `received` for what the line landed once it is
  not.

**Screen-independent (U1).** Each PO line and each transferred allocation is a pool the
placements share in the order they were made (`linked_at, id`), over EVERY live placement on
the PO line, whatever the caller asked for; `_holds` shared it only among the placements on the
SO lines it was reading. Asking for one placement or for the whole book now gives that
placement the same hops.

**Received semantics (U2, owner rulings Q3 to Q6, 26 Oct 2026).**

* Q3: a PO placement is received when the goods land on the SPO it was transferred onto, never
  on the transfer itself (`is_received`).
* Q4: a PO line transferred with no SPO under the key (a local PO received straight into a
  bin) is `received_direct` for what it transferred less what a Cancel PO took.
* Q5: a document that brings nothing is `dead`, qty 0, the placement left in place: a PO line
  cancelled or closed with nothing transferred, or wholly taken by a Cancel PO
  (`po_cancelled`); an SPO line retired with nothing received, or closed with nothing landed
  (`spo_withdrawn`).
* Q6: a `received` or `received_direct` hop sits where the Goods Received documents naming
  its document say the goods went, one hop per bin, GR lines earliest first and handed to the
  placements in the order they were made; what no GR line covers stays at the document's own
  bin.

Out on purpose: whether the goods are still in the bin (Stock Debt's `found_empty` and the
`assign()` floors), ETA wording, and the book-text S/O pins. The chain says where the goods
were received, not what the bin holds now.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, func, or_, tuple_
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PickingHeader,
    PickingLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryLink, OrderInquiryRow
from app.services.company_scope import build_company_predicate
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import spo_supply
from app.services.scm.container_request_service import OPEN_PO_STATUSES
from app.services.scm.spo_conversion_service import SOURCE_SYSTEM as CRM_SPO_SOURCE_SYSTEM
from app.services.scm.supply_assignment import EPSILON

#: Hop states (plan section 4).
ON_ORDER = "on_order"
IN_TRANSIT = "in_transit"
RECEIVED = "received"
RECEIVED_DIRECT = "received_direct"
DEAD = "dead"

#: The states whose goods have landed in a bin: what `is_received` and `received_qty` count.
RECEIVED_STATES = (RECEIVED, RECEIVED_DIRECT)

#: Why a hop is `dead` (Q5).
PO_CANCELLED = "po_cancelled"
SPO_WITHDRAWN = "spo_withdrawn"

KIND_PO = "po"
KIND_SPO = "spo"

#: The Goods Received documents that count: the two tests the CRM receipt recompute reads
#: (`procurement_service.get_received_quantities_by_product`). The AutoCount feed writes a
#: cancelled or vanished GR as `picking_status = 'cancelled'`, so the same tests serve both.
_GR_TYPE = "goods_received"
_GR_STATUS = "approved"

_ZERO = Decimal("0")
_EPSILON = Decimal(str(EPSILON))


@dataclass(frozen=True)
class Hop:
    """One leg of where a placement's quantity is: on a PO line (`kind` `po`) or on an SPO
    allocation (`kind` `spo`). `warehouse_*` is set on a `received` / `received_direct` hop
    only, the bin the goods were received at."""

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
    #: `po_cancelled` | `spo_withdrawn` on a `dead` hop.
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


def received_qty(chain: LinkChain) -> Decimal:
    """The placement's own quantity that has landed in a bin (Q3): its `received` and
    `received_direct` hops, never the document's whole receipt."""
    return sum((hop.qty for hop in chain.hops if hop.state in RECEIVED_STATES), _ZERO)


def is_received(chain: LinkChain) -> bool:
    """Every unit of the placement has landed (Q3): all of it in `received` /
    `received_direct` hops, nothing in transit, on order or unplaced."""
    return (
        chain.placed_qty > _EPSILON
        and received_qty(chain) >= chain.placed_qty - _EPSILON
    )


def is_in_transit(spo: Any) -> bool:
    """An SPO allocation row (the `spo_*` columns) still on the water: it passes
    `open_incoming_clauses()` and has more allocated than received."""
    return bool(spo.spo_incoming) and _float(spo.spo_allocated) > _float(spo.spo_received)


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


def _transfer_key(row: Any) -> Tuple[str, str, str, str]:
    """OI-SPO-EXACT plus company, off a PO line row carrying `po_number`, `po_line_ref`
    (trimmed), `po_product_id` and `po_company_id`."""
    return (
        row.po_number,
        row.po_line_ref,
        str(row.po_product_id),
        str(row.po_company_id),
    )


def transferred_allocations(
    db: Session, po_lines: Sequence[Any], *, include_withdrawn: bool = False
) -> Dict[str, List[Any]]:
    """SUPPLY-SPO-LINK: by PO line id, the SPO allocations each line in `po_lines` (rows
    carrying `po_line_id` and the `_transfer_key` columns) was transferred onto, earliest
    arrival first. One read for every line. `include_withdrawn` (LINKAGE-UNIFY U4, the PO
    screens' SPO column) keeps a retired line with nothing received too, so the screen can
    say it was withdrawn; `spo_visible` on each row tells the two apart.

    Two routes, one answer, an allocation reached both ways listed once:

    * OI-SPO-EXACT, the key `project_order_inquiry_service._append_derived_spo_entries`
      resolves a PO link's SPOs by: `from_po_number`, trimmed `from_po_line_ref`, product
      and company, for an allocation off the AutoCount feed. A PO line with no `source_ref`
      reaches nothing this way;
    * the allocation's own `po_line_id`, for one this system raised off the line
      (`allocation_suggestion_service.approve`), in the line's company.

    Not followed yet: a CRM-converted SPO (`spo_conversion_service.create`) points its
    allocation's `po_line_id` at the CRM SPO's own new PO line and names the source PO line
    only in that line's `pulls` JSON. Trigger to build that route: the first `crm_spo` PO
    line carrying `pulls` in the data (0 on the dev copy, 26 Oct 2026).

    Every visible allocation, not only the open ones: a landed allocation is where the
    goods ARE, and the split turns it into a `received` hop. The company is part of both
    routes (LINKAGE-UNIFY AC-R8): the text key is plain text off the AutoCount feed, so
    another company's SPO naming the same strings is not this line's, whatever the
    session's scope. The scope predicate is stated by hand too, as the OI reader states it.
    """
    company_of: Dict[str, str] = {}
    lines_by_key: Dict[Tuple[str, str, str, str], Set[str]] = {}
    for row in po_lines:
        if not row.po_line_id:
            continue
        line_id = str(row.po_line_id)
        company_of[line_id] = str(row.po_company_id)
        if row.po_number and row.po_line_ref and row.po_product_id and row.po_company_id:
            lines_by_key.setdefault(_transfer_key(row), set()).add(line_id)
    if not company_of:
        return {}
    routes = [SPOAllocation.po_line_id.in_(sorted(company_of))]
    if lines_by_key:
        routes.append(
            tuple_(
                SPOAllocation.from_po_number,
                func.btrim(SPOAllocation.from_po_line_ref),
                SPOAllocation.product_id,
                SPOAllocation.company_id,
            ).in_(sorted(lines_by_key))
        )
    company_predicate = build_company_predicate(SPOAllocation, get_company_scope(db))
    rows = (
        db.query(
            SPOAllocation.from_po_number,
            func.btrim(SPOAllocation.from_po_line_ref).label("from_ref"),
            SPOAllocation.po_line_id.label("spo_po_line_id"),
            SPOAllocation.id.label("spo_allocation_id"),
            SPOAllocation.spo_number,
            SPOAllocation.spo_line_number,
            and_(*spo_supply.open_incoming_clauses()).label("spo_incoming"),
            SPOAllocation.allocated_quantity.label("spo_allocated"),
            SPOAllocation.quantity_received.label("spo_received"),
            SPOAllocation.receipt_status.label("spo_receipt_status"),
            SPOAllocation.product_id.label("spo_product_id"),
            SPOAllocation.company_id.label("spo_company_id"),
            SPOAllocation.warehouse_id.label("spo_warehouse_id"),
            Warehouse.warehouse_code.label("spo_warehouse_code"),
            InboundShipment.actual_arrival_date.label("spo_arrived"),
            and_(*spo_supply.visible_line_clauses()).label("spo_visible"),
        )
        .outerjoin(
            InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
        )
        .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .filter(
            or_(*routes),
            *(() if include_withdrawn else spo_supply.visible_line_clauses()),
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
    out: Dict[str, List[Any]] = {}
    for row in rows:
        lines = set(
            lines_by_key.get(
                (
                    row.from_po_number,
                    row.from_ref,
                    str(row.spo_product_id),
                    str(row.spo_company_id),
                ),
                (),
            )
        )
        named = str(row.spo_po_line_id) if row.spo_po_line_id else None
        if named in company_of and company_of[named] == str(row.spo_company_id):
            lines.add(named)
        for line_id in lines:
            out.setdefault(line_id, []).append(row)
    return out


@dataclass(frozen=True)
class Placement:
    """LINKAGE-UNIFY U4: one live placement whose goods pass through a document asked about
    (`placements_on`)."""

    chain: LinkChain
    #: The PO line or SPO allocation id it is reported for.
    document_id: str
    #: What of the placement sits on that document: all of it on the line it names; for an
    #: SPO reached through a PO line, the chain's hops on that SPO.
    qty: Decimal
    #: The PO number a placement reached an SPO through (it follows its PO line onto it);
    #: None on the document the placement names itself.
    via_po: Optional[str] = None


def placements_on(
    db: Session,
    po_line_ids: Iterable[str] = (),
    spo_allocation_ids: Iterable[str] = (),
    *,
    with_bins: bool = True,
) -> List[Placement]:
    """LINKAGE-UNIFY U4: every live placement whose chain passes through these documents,
    each with its chain (the same split, GR bins and dead rules as every other reader). A
    placement on a PO line is reported for the PO line; for an SPO it is reported when it
    names the SPO itself, and, marked `via_po`, when its PO line's goods follow onto it."""
    po_ids = sorted({str(i) for i in po_line_ids if i})
    spo_ids = sorted({str(i) for i in spo_allocation_ids if i})
    out: List[Placement] = []
    if po_ids:
        rows = _placements(db, OrderInquiryLink.po_line_id.in_(po_ids))
        chains = _chains(db, rows, with_bins=with_bins)
        out.extend(
            Placement(
                chain=chains[str(row.link_id)],
                document_id=str(row.po_line_id),
                qty=_dec(row.qty),
            )
            for row in rows
        )
    if spo_ids:
        direct = _placements(db, OrderInquiryLink.spo_allocation_id.in_(spo_ids))
        sources = (
            db.query(
                SPOAllocation.from_po_number.label("spo_from_po_number"),
                func.btrim(SPOAllocation.from_po_line_ref).label("spo_from_ref"),
                SPOAllocation.po_line_id.label("spo_po_line_id"),
                SPOAllocation.product_id.label("spo_product_id"),
                SPOAllocation.company_id.label("spo_company_id"),
            )
            .filter(SPOAllocation.id.in_(spo_ids))
            .all()
        )
        feeding = _po_lines_feeding(db, sources)
        followers = (
            _placements(db, OrderInquiryLink.po_line_id.in_(sorted(feeding))) if feeding else []
        )
        chains = _chains(db, [*direct, *followers], with_bins=with_bins)
        out.extend(
            Placement(
                chain=chains[str(row.link_id)],
                document_id=str(row.spo_allocation_id),
                qty=_dec(row.qty),
            )
            for row in direct
        )
        wanted = set(spo_ids)
        for row in followers:
            chain = chains[str(row.link_id)]
            on: Dict[str, Decimal] = {}
            for hop in chain.hops:
                if (
                    hop.kind == KIND_SPO
                    and hop.spo_allocation_id in wanted
                    and hop.state in (IN_TRANSIT, RECEIVED)
                ):
                    on[hop.spo_allocation_id] = on.get(hop.spo_allocation_id, _ZERO) + hop.qty
            out.extend(
                Placement(chain=chain, document_id=allocation_id, qty=qty, via_po=row.po_number)
                for allocation_id, qty in on.items()
            )
    return out


def spo_lines_of(db: Session, po_line_ids: Iterable[str]) -> Dict[str, List[Dict[str, Any]]]:
    """LINKAGE-UNIFY U4: by PO line id, every SPO line it was transferred onto (either
    route, a withdrawn one included), for the PO screens' SPO column - `spo_number`,
    `line_label`, `receipts` (where the SPO line's landed goods sit, per GR bin: the whole
    line's, not one placement's share) and `dead_reason` (`spo_withdrawn`: retired with
    nothing received, or closed with nothing landed). A line in transit has neither."""
    ids = sorted({str(i) for i in po_line_ids if i})
    if not ids:
        return {}
    lines = (
        db.query(
            PurchaseOrderLine.id.label("po_line_id"),
            PurchaseOrder.po_number,
            func.btrim(PurchaseOrderLine.source_ref).label("po_line_ref"),
            PurchaseOrderLine.product_id.label("po_product_id"),
            PurchaseOrderLine.company_id.label("po_company_id"),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrderLine.id.in_(ids))
        .all()
    )
    transferred = transferred_allocations(db, lines, include_withdrawn=True)
    landed: Dict[str, Decimal] = {}
    for spos in transferred.values():
        for spo in spos:
            if spo.spo_visible and not is_in_transit(spo):
                landed[str(spo.spo_allocation_id)] = _dec(
                    landed_qty(
                        _float(spo.spo_allocated),
                        _float(spo.spo_received),
                        arrived=spo.spo_arrived is not None,
                        receipt_status=spo.spo_receipt_status,
                    )
                )
    grs, codes = _gr_lines(
        db, {allocation for allocation, qty in landed.items() if qty > _EPSILON}, {}
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for line_id, spos in transferred.items():
        entries: List[Dict[str, Any]] = []
        for spo in spos:
            allocation_id = str(spo.spo_allocation_id)
            qty = landed.get(allocation_id, _ZERO)
            receipts: List[Dict[str, Any]] = []
            dead_reason = None
            if not spo.spo_visible or (not is_in_transit(spo) and qty <= _EPSILON):
                dead_reason = SPO_WITHDRAWN
            elif qty > _EPSILON:
                own = str(spo.spo_warehouse_id) if spo.spo_warehouse_id else None
                pieces = _take_from_pool(
                    [[bin_id, left] for bin_id, left in grs.get((KIND_SPO, allocation_id), ())],
                    qty,
                    own,
                )
                receipts = [
                    {
                        "qty": format(piece.normalize(), "f"),
                        "bin": codes.get(bin_id or "")
                        or (spo.spo_warehouse_code if bin_id == own else None),
                    }
                    for bin_id, piece in pieces.items()
                ]
            entries.append(
                {
                    "spo_number": spo.spo_number,
                    "line_label": f"L{spo.spo_line_number}"
                    if spo.spo_line_number is not None
                    else None,
                    "receipts": receipts,
                    "dead_reason": dead_reason,
                }
            )
        out[line_id] = entries
    return out


def chains_for_links(
    db: Session, link_ids: Iterable[str], *, with_bins: bool = True
) -> Dict[str, LinkChain]:
    """By link id, the chain of each live placement in `link_ids`. A link on a cancelled
    order inquiry row, or a reserve link (no document line), is absent.

    `with_bins=False` skips the Goods Received bin split (and the reads only it needs): a
    landed hop then sits whole at its document's own bin. For a caller that only asks
    whether, or how much, is received (`is_received`, `received_qty`), which bins do not
    change."""
    ids = sorted({str(link_id) for link_id in link_ids if link_id})
    if not ids:
        return {}
    return _chains(db, _placements(db, OrderInquiryLink.id.in_(ids)), with_bins=with_bins)


def chains_for_rows(
    db: Session, row_ids: Iterable[str], *, with_bins: bool = True
) -> Dict[str, List[LinkChain]]:
    """By order inquiry row id, the chains of the row's live placements in `linked_at, id`
    order. A row with none (cancelled, or nothing placed) is absent. `with_bins` as
    `chains_for_links`."""
    ids = sorted({str(row_id) for row_id in row_ids if row_id})
    if not ids:
        return {}
    wanted = _placements(db, OrderInquiryLink.row_id.in_(ids))
    chains = _chains(db, wanted, with_bins=with_bins)
    out: Dict[str, List[LinkChain]] = {}
    for row in wanted:
        out.setdefault(str(row.row_id), []).append(chains[str(row.link_id)])
    return out


def _placements(db: Session, *criteria: Any) -> List[Any]:
    """The live placements matching `criteria`, made-first first, each with the columns of
    the document line it names. Live: the order inquiry row is not cancelled and the link
    names a PO or SPO line. A retired SPO line with nothing received stays in the read, so
    its placement still answers (a `dead` hop); `spo_visible` says which it is."""
    return (
        db.query(
            OrderInquiryLink.id.label("link_id"),
            OrderInquiryLink.row_id,
            OrderInquiryLink.qty,
            OrderInquiryLink.linked_at,
            OrderInquiryLink.spo_allocation_id,
            OrderInquiryLink.po_line_id,
            SPOAllocation.spo_number,
            SPOAllocation.spo_line_number,
            and_(*spo_supply.visible_line_clauses()).label("spo_visible"),
            # The shared incoming rule, evaluated in SQL on the row itself; the quantity
            # half is applied in `is_in_transit`, beside the arithmetic. NULL-safe for a PO
            # link.
            and_(*spo_supply.open_incoming_clauses()).label("spo_incoming"),
            SPOAllocation.allocated_quantity.label("spo_allocated"),
            SPOAllocation.quantity_received.label("spo_received"),
            SPOAllocation.receipt_status.label("spo_receipt_status"),
            SPOAllocation.warehouse_id.label("spo_warehouse_id"),
            Warehouse.warehouse_code.label("spo_warehouse_code"),
            InboundShipment.actual_arrival_date.label("spo_arrived"),
            # The PO line an SPO line names as its source (the key read backwards), so a
            # placement on the SPO can find the placements that follow onto it.
            SPOAllocation.from_po_number.label("spo_from_po_number"),
            func.btrim(SPOAllocation.from_po_line_ref).label("spo_from_ref"),
            SPOAllocation.po_line_id.label("spo_po_line_id"),
            SPOAllocation.product_id.label("spo_product_id"),
            SPOAllocation.company_id.label("spo_company_id"),
            # Is the placed PO line still on order (`_po_rows`'s own test), and what did it
            # transfer? NULL for an SPO link, whose branch never reads them.
            and_(*ProjectSupplyService.open_po_line_clauses()).label("po_open"),
            PurchaseOrderLine.qty_ordered.label("po_ordered"),
            PurchaseOrderLine.qty_received.label("po_received"),
            PurchaseOrderLine.qty_cancelled.label("po_cancelled"),
            PurchaseOrderLine.line_status.label("po_line_status"),
            func.btrim(PurchaseOrderLine.source_ref).label("po_line_ref"),
            PurchaseOrderLine.product_id.label("po_product_id"),
            PurchaseOrderLine.warehouse_id.label("po_warehouse_id"),
            PurchaseOrderLine.company_id.label("po_company_id"),
            PurchaseOrder.po_number,
            PurchaseOrder.id.label("purchase_order_id"),
            PurchaseOrder.status.label("po_status"),
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


def _chains(
    db: Session, wanted: Sequence[Any], *, with_bins: bool
) -> Dict[str, LinkChain]:
    """The chain of each placement in `wanted` (rows of `_placements`).

    The answer for one placement can depend on others that share its documents, so they
    are read too, whatever the caller asked for: every live placement on each PO line asked
    about (the split), and, for a document whose goods landed, every placement holding some
    of them (who takes which GR bin first; only `with_bins`). A placement on an SPO that
    landed brings in the PO lines that SPO names, since placements on those follow onto
    it."""
    rows: Dict[str, Any] = {str(row.link_id): row for row in wanted}
    hops: Dict[str, List[Hop]] = {
        str(row.link_id): _direct_hops(row) for row in wanted if row.spo_allocation_id
    }
    landed_spos = _landed_spo_ids(hops.values())
    po_line_ids = {
        str(row.po_line_id) for row in wanted if not row.spo_allocation_id and row.po_line_id
    }
    if with_bins:
        po_line_ids |= _po_lines_feeding(
            db,
            [
                row for row in wanted
                if row.spo_allocation_id and str(row.spo_allocation_id) in landed_spos
            ],
        )
    if po_line_ids:
        everyone = _placements(db, OrderInquiryLink.po_line_id.in_(sorted(po_line_ids)))
        rows.update((str(row.link_id), row) for row in everyone)
        hops.update(_po_split(db, everyone))
        landed_spos |= _landed_spo_ids(hops.values())
    if with_bins:
        if landed_spos:
            for row in _placements(
                db, OrderInquiryLink.spo_allocation_id.in_(sorted(landed_spos))
            ):
                if str(row.link_id) not in hops:
                    rows[str(row.link_id)] = row
                    hops[str(row.link_id)] = _direct_hops(row)
        _bin_by_gr(db, hops, rows)
    return {
        str(row.link_id): LinkChain(
            link_id=str(row.link_id),
            row_id=str(row.row_id),
            placed_qty=_dec(row.qty),
            hops=tuple(hops.get(str(row.link_id), ())),
        )
        for row in wanted
    }


def _landed_spo_ids(legs: Iterable[List[Hop]]) -> Set[str]:
    return {
        str(hop.spo_allocation_id)
        for hops in legs
        for hop in hops
        if hop.state == RECEIVED and hop.spo_allocation_id
    }


def _po_lines_feeding(db: Session, spo_rows: Sequence[Any]) -> Set[str]:
    """The ids of the PO lines the SPO lines of `spo_rows` were transferred from, by the
    same two routes `transferred_allocations` reads forwards."""
    named = {str(row.spo_po_line_id) for row in spo_rows if row.spo_po_line_id}
    keys = {
        (
            row.spo_from_po_number,
            row.spo_from_ref,
            str(row.spo_product_id),
            str(row.spo_company_id),
        )
        for row in spo_rows
        if row.spo_from_po_number and row.spo_from_ref and row.spo_product_id
    }
    if not keys:
        return named
    company_predicate = build_company_predicate(PurchaseOrderLine, get_company_scope(db))
    return named | {
        str(line_id)
        for (line_id,) in db.query(PurchaseOrderLine.id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            tuple_(
                PurchaseOrder.po_number,
                func.btrim(PurchaseOrderLine.source_ref),
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.company_id,
            ).in_(sorted(keys)),
            *((company_predicate,) if company_predicate is not None else ()),
        )
        .all()
    }


def po_line_on_order(
    *, po_status: Any, line_status: Any, ordered: Any, received: Any, source_system: Any
) -> bool:
    """Python spelling of `ProjectSupplyService.open_po_line_clauses` for a PO line already
    in hand (the PO screens' line builders), so `po_line_is_dead` reads the same `on_order`
    the placement query's `po_open` column does."""
    return (
        po_status in OPEN_PO_STATUSES
        and line_status == "open"
        and _dec(ordered) > _dec(received)
        and (source_system or "") != CRM_SPO_SOURCE_SYSTEM
    )


def po_line_is_dead(
    *,
    has_spo: bool,
    ordered: Any,
    received: Any,
    cancelled: Any,
    on_order: bool,
    line_status: Any,
    po_status: Any,
) -> bool:
    """Q5, the ONE dead-PO-line rule: no SPO under the PO->SPO key, nothing moved past what
    a Cancel PO took, nothing left on order, and the line was closed or cancelled, its PO
    cancelled, or a Cancel PO took it all. `qty_received` is the AutoCount transfer and
    includes what a Cancel PO took. The chain and the PO screens' line builders share it."""
    left = max(_dec(ordered) - _dec(received), _ZERO) if on_order else _ZERO
    moved = max(_dec(received) - _dec(cancelled), _ZERO)
    return (
        not has_spo
        and moved <= _EPSILON
        and left <= _EPSILON
        and (
            line_status in ("closed", "cancelled")
            or po_status == "cancelled"
            or _dec(received) > _EPSILON
        )
    )


def _po_split(db: Session, placements: Sequence[Any]) -> Dict[str, List[Hop]]:
    """By link id, the hops of each placement on a PO line (SUPPLY-SPO-LINK). `placements`
    is every live placement on the lines, made-first first: each transferred allocation,
    each line's received goods (class d) and each line's on-order rest is a pool they share
    in that order, so two placements never claim the same units.

    The goods that moved first are handed out first: what the line transferred (onto its
    SPOs, or straight into a bin when no SPO names it, Q4), then what it still has on order.
    A line that brings nothing at all is `dead` (Q5); one that is merely used up by earlier
    placements gives a later placement no hop."""
    transferred_to = transferred_allocations(db, placements)

    def spos_of(row: Any) -> List[Any]:
        return transferred_to.get(str(row.po_line_id), [])

    po_left: Dict[str, Decimal] = {}
    direct_left: Dict[str, Decimal] = {}
    dead: Set[str] = set()
    for row in placements:
        line_id = str(row.po_line_id)
        po_left[line_id] = (
            max(_dec(row.po_ordered) - _dec(row.po_received), _ZERO) if row.po_open else _ZERO
        )
        # `qty_received` is the AutoCount transfer and includes what a Cancel PO took.
        moved = max(_dec(row.po_received) - _dec(row.po_cancelled), _ZERO)
        direct_left[line_id] = _ZERO if spos_of(row) else moved
        if po_line_is_dead(
            has_spo=bool(spos_of(row)),
            ordered=row.po_ordered,
            received=row.po_received,
            cancelled=row.po_cancelled,
            on_order=bool(row.po_open),
            line_status=row.po_line_status,
            po_status=row.po_status,
        ):
            # Q5: nothing left on order, nothing moved past what a Cancel PO took, and no
            # SPO to follow: the line was closed or cancelled, or a Cancel PO took it all.
            dead.add(line_id)
    spo_left: Dict[str, Decimal] = {
        str(spo.spo_allocation_id): _dec(follow_capacity(spo))
        for spos in transferred_to.values()
        for spo in spos
    }
    out: Dict[str, List[Hop]] = {}
    for row in placements:
        line_id = str(row.po_line_id)
        hops: List[Hop] = []
        out[str(row.link_id)] = hops
        rest = _dec(row.qty)
        if rest <= 0:
            continue
        if line_id in dead:
            hops.append(_po_hop(row, DEAD, _ZERO, reason=PO_CANCELLED))
            continue
        for spo in spos_of(row):
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
        take = min(rest, direct_left[line_id])
        if take > _EPSILON:
            direct_left[line_id] -= take
            rest -= take
            # The PO line's own bin until a GR line says otherwise (`_bin_by_gr`).
            hops.append(
                _po_hop(
                    row,
                    RECEIVED_DIRECT,
                    take,
                    warehouse_id=str(row.po_warehouse_id) if row.po_warehouse_id else None,
                )
            )
        take = min(rest, po_left[line_id])
        if take <= _EPSILON:
            continue
        po_left[line_id] -= take
        hops.append(_po_hop(row, ON_ORDER, take))
    return out


def _po_hop(
    row: Any,
    state: str,
    qty: Decimal,
    *,
    warehouse_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> Hop:
    return Hop(
        kind=KIND_PO,
        state=state,
        qty=qty,
        po_line_id=str(row.po_line_id),
        po_number=row.po_number,
        purchase_order_id=str(row.purchase_order_id) if row.purchase_order_id else None,
        warehouse_id=warehouse_id,
        reason=reason,
    )


def _direct_hops(row: Any) -> List[Hop]:
    """The hop of a placement straight on an SPO line: the SPO rule (`_spo_hop`), or `dead`
    (Q5) for a line retired with nothing received or one that will bring nothing."""
    placed = _dec(row.qty)
    if placed <= 0:
        return []
    hop = _spo_hop(row, placed) if row.spo_visible else None
    if hop is not None:
        return [hop]
    return [
        Hop(
            kind=KIND_SPO,
            state=DEAD,
            qty=_ZERO,
            spo_allocation_id=str(row.spo_allocation_id),
            spo_number=row.spo_number,
            spo_line_number=row.spo_line_number,
            reason=SPO_WITHDRAWN,
        )
    ]


def _spo_hop(spo: Any, qty: Decimal) -> Optional[Hop]:
    """`qty` of a placement on one SPO allocation (`spo`, a row carrying the `spo_*`
    columns): `in_transit` while the line is incoming, else `received` for what it landed
    (SPO-RECEIVED-PIN), at its bin. None when it landed nothing."""
    if is_in_transit(spo):
        return Hop(
            kind=KIND_SPO,
            state=IN_TRANSIT,
            qty=qty,
            spo_allocation_id=str(spo.spo_allocation_id),
            spo_number=spo.spo_number,
            spo_line_number=spo.spo_line_number,
        )
    landed = landed_qty(
        _float(spo.spo_allocated),
        _float(spo.spo_received),
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


def _bin_by_gr(db: Session, hops: Dict[str, List[Hop]], rows: Dict[str, Any]) -> None:
    """Q4/Q6, in place: each `received` / `received_direct` hop split over the bins the
    Goods Received lines naming its document put the goods in, one hop per bin.

    A document's GR lines are a pool, earliest first (`picking_date`, then line), handed to
    the placements holding its goods in the order they were made, as the split hands out
    the documents themselves. What no GR line covers stays at the document's own bin, and
    so does a GR line whose bin cannot be resolved."""
    claims: Dict[Tuple[str, str], List[Tuple[Any, str, int]]] = {}
    for link_id, legs in hops.items():
        for index, hop in enumerate(legs):
            if hop.state == RECEIVED and hop.spo_allocation_id:
                document = (KIND_SPO, hop.spo_allocation_id)
            elif hop.state == RECEIVED_DIRECT and hop.po_line_id:
                document = (KIND_PO, hop.po_line_id)
            else:
                continue
            claims.setdefault(document, []).append(
                ((rows[link_id].linked_at, link_id), link_id, index)
            )
    if not claims:
        return
    po_rows: Dict[str, Any] = {}
    for link_id, legs in hops.items():
        for hop in legs:
            if hop.state == RECEIVED_DIRECT and hop.po_line_id:
                po_rows.setdefault(hop.po_line_id, rows[link_id])
    spo_ids = {document_id for kind, document_id in claims if kind == KIND_SPO}
    grs, codes = _gr_lines(db, spo_ids, po_rows)
    split: Dict[Tuple[str, int], List[Hop]] = {}
    for document, claimants in claims.items():
        pool = [[bin_id, qty] for bin_id, qty in grs.get(document, ())]
        for _order, link_id, index in sorted(claimants):
            hop = hops[link_id][index]
            pieces = _take_from_pool(pool, hop.qty, hop.warehouse_id)
            split[(link_id, index)] = [
                replace(
                    hop,
                    qty=qty,
                    warehouse_id=bin_id,
                    warehouse_code=codes.get(bin_id or "")
                    or (hop.warehouse_code if bin_id == hop.warehouse_id else None),
                )
                for bin_id, qty in pieces.items()
            ]
    for link_id, legs in hops.items():
        if any((link_id, index) in split for index in range(len(legs))):
            hops[link_id] = [
                piece
                for index, hop in enumerate(legs)
                for piece in split.get((link_id, index), [hop])
            ]


def _take_from_pool(
    pool: List[List[Any]], amount: Decimal, own_bin: Optional[str]
) -> Dict[Optional[str], Decimal]:
    """`amount` taken off a document's GR lines (`[[bin id, qty left], ...]`, earliest
    first, spent in place), as `{bin id: qty}`; what no GR line covers, and a GR line with
    no bin, sits at `own_bin`, the document's own."""
    pieces: Dict[Optional[str], Decimal] = {}
    for line in pool:
        if amount <= _EPSILON:
            break
        take = min(amount, line[1])
        if take <= _EPSILON:
            continue
        line[1] -= take
        amount -= take
        bin_id = line[0] or own_bin
        pieces[bin_id] = pieces.get(bin_id, _ZERO) + take
    if amount > _EPSILON:
        pieces[own_bin] = pieces.get(own_bin, _ZERO) + amount
    return pieces


def _gr_lines(
    db: Session, spo_ids: Set[str], po_rows: Dict[str, Any]
) -> Tuple[Dict[Tuple[str, str], List[Tuple[Optional[str], Decimal]]], Dict[str, str]]:
    """The Goods Received lines naming each document, earliest first, as `(bin id, qty)`
    (bin None when it cannot be resolved), and the warehouse code of every bin involved.

    An AutoCount GR (`doc_key` set) names its PO or SPO line itself; its bin is
    `destination_warehouse_id` (the ingest resolves the GR's location there,
    `autocount_doc_ingest_service._apply_grn`) and its quantity `qty`. An Excel GR
    (`doc_key` NULL) names an SPO line by `spo_allocation_id`, but a PO line only through its
    header `spo_number` (where it holds the PO number) and the product, which says which
    line only when the PO has one line of that product; its bin is `source_warehouse_id`
    and its quantity `quantity_picked` (plan section 5a)."""
    counts = (
        PickingHeader.picking_type == _GR_TYPE,
        PickingHeader.picking_status == _GR_STATUS,
    )
    columns = (
        PickingLine.id,
        PickingHeader.picking_date,
        PickingHeader.doc_key,
        PickingLine.spo_allocation_id,
        PickingLine.po_line_id,
        PickingLine.qty,
        PickingLine.quantity_picked,
        PickingLine.destination_warehouse_id,
        PickingLine.source_warehouse_id,
        PickingLine.company_id,
    )
    found: List[Tuple[Tuple[str, str], Any]] = []
    named = []
    if spo_ids:
        named.append(PickingLine.spo_allocation_id.in_(sorted(spo_ids)))
    if po_rows:
        named.append(
            and_(
                PickingLine.po_line_id.in_(sorted(po_rows)),
                PickingHeader.doc_key.isnot(None),
            )
        )
    for line in (
        db.query(*columns)
        .join(PickingHeader, PickingHeader.id == PickingLine.picking_header_id)
        .filter(*counts, or_(*named))
        .all()
    ):
        if line.spo_allocation_id and str(line.spo_allocation_id) in spo_ids:
            found.append(((KIND_SPO, str(line.spo_allocation_id)), line))
        elif line.po_line_id and str(line.po_line_id) in po_rows:
            found.append(((KIND_PO, str(line.po_line_id)), line))
    excel = _single_product_po_lines(db, po_rows)
    if excel:
        for line in (
            db.query(*columns, PickingHeader.spo_number, PickingLine.product_id)
            .join(PickingHeader, PickingHeader.id == PickingLine.picking_header_id)
            .filter(
                *counts,
                PickingHeader.doc_key.is_(None),
                PickingLine.spo_allocation_id.is_(None),
                tuple_(PickingHeader.spo_number, PickingLine.product_id).in_(
                    sorted({(number, product) for number, product, _company in excel})
                ),
            )
            .all()
        ):
            line_id = excel.get(
                (line.spo_number, str(line.product_id), str(line.company_id))
            )
            if line_id:
                found.append(((KIND_PO, line_id), line))

    out: Dict[Tuple[str, str], List[Tuple[Optional[str], Decimal]]] = {}
    for document, line in sorted(found, key=lambda item: (item[1].picking_date, str(item[1].id))):
        if line.doc_key is not None:
            qty = _dec(line.qty if line.qty is not None else line.quantity_picked)
            bin_id = line.destination_warehouse_id
        else:
            qty = _dec(line.quantity_picked)
            bin_id = line.source_warehouse_id
        if qty > _EPSILON:
            out.setdefault(document, []).append((str(bin_id) if bin_id else None, qty))

    bin_ids = {bin_id for lines in out.values() for bin_id, _qty in lines if bin_id}
    bin_ids |= {str(row.po_warehouse_id) for row in po_rows.values() if row.po_warehouse_id}
    codes: Dict[str, str] = {}
    if bin_ids:
        codes = {
            str(warehouse_id): code
            for warehouse_id, code in db.query(Warehouse.id, Warehouse.warehouse_code).filter(
                Warehouse.id.in_(sorted(bin_ids))
            )
        }
    return out, codes


def _single_product_po_lines(
    db: Session, po_rows: Dict[str, Any]
) -> Dict[Tuple[str, str, str], str]:
    """`(po_number, product_id, company_id) -> po_line_id` for each line in `po_rows` that is
    the only line of its product on its PO: the lines an Excel GR can name."""
    order_ids = {str(row.purchase_order_id) for row in po_rows.values() if row.purchase_order_id}
    if not order_ids:
        return {}
    alone = {
        (str(order_id), str(product_id))
        for order_id, product_id, lines in db.query(
            PurchaseOrderLine.purchase_order_id,
            PurchaseOrderLine.product_id,
            func.count(PurchaseOrderLine.id),
        )
        .filter(PurchaseOrderLine.purchase_order_id.in_(sorted(order_ids)))
        .group_by(PurchaseOrderLine.purchase_order_id, PurchaseOrderLine.product_id)
        .all()
        if lines == 1
    }
    return {
        (row.po_number, str(row.po_product_id), str(row.po_company_id)): line_id
        for line_id, row in po_rows.items()
        if row.po_number and (str(row.purchase_order_id), str(row.po_product_id)) in alone
    }
