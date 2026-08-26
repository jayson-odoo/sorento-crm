""""Create SPO" - a shipment's uncovered lines become a real CRM purchase order.

`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision: "Separate button after
packing-list apply. The shipment page gets a Create SPO action she presses when ready.
Suggestion logic as originally planned (match open PO lines by product / stated po_ref /
delivery date, net on hand + incoming SPO), but the BASE quantity is the PACKED qty, not the
invoice qty."

Two moves, two functions, the same shape as `container_request_service` (`build` / `send`)
and `proforma_invoice_service` (`convert_to_draft_shipment`):

  * `suggest` - a pure read. Per shipment line: the PACKED quantity (`quantity_shipped`,
    never the PI's invoiced figure - the Amendment's own correction), what an OPEN purchase
    order to the SAME supplier already covers (matched by product, PINNED to one PO when the
    line's originating PI line(s) stated a `po_ref`), and on hand + incoming SPO company-wide
  - same three figures `container_request_service._stock_context` reads, same reason: this
    is one company deciding what it still needs, not one warehouse's question. The suggested
    qty is `packed - po_covered - on_hand - incoming_spo`, floored at zero, editable. A line
    with nothing left to ask for reads as COVERED (unticked by default, one line saying why);
    a line with no supplier at all cannot convert (a container with an unattributed factory
    line, the n8n PDF path) and says so.
  * `create` - writes ONE `purchase_orders` header per SUPPLIER represented on the shipment
    (a container is routinely several factories' goods, and AutoCount POs are per supplier
    too), lines carrying the confirmed quantities, source-marked `SOURCE_SYSTEM` so it can
    never be mistaken for an AutoCount import. Idempotent by refusal: a shipment with ANY
    existing `ShipmentLineSpoLink` row is refused with a 409 naming the SPOs it already made,
    the same shape `proforma_invoice_service.convert_to_draft_shipment` uses for the PI
    convert this composes with.

**Where the new SPO counts as supply.** `scm.po_ordered_v` reads `purchase_order_lines`
by STATUS and LINE_STATUS only - no `source_system` predicate - so an `active` / `open` CRM
SPO line is counted as "ordered" the moment it is created, exactly like an AutoCount import
would be (migration 337's `PO_ORDERED_V`). `scm.on_order_v` reads `spo_allocations`
exclusively and is UNCHANGED by this module on purpose: an allocation is a WAREHOUSE decision
(which location this shipment's goods land in), a separate, later, explicit step
(`allocation_suggestion_service.approve` / `SPOAllocationService.create_allocation`) that
this action does not take for her - `po_history_service`'s own SPO-history rows draw the
identical line (deliberately NOT written to `spo_allocations` either). So a freshly created
CRM SPO shows as ORDERED on every book/reorder screen immediately; it becomes INCOMING SPO
supply only once somebody allocates it to a warehouse, same as any other SPO.

**Reconciliation** (the next AutoCount book import matching this SPO by number) is explicitly
OUT OF SCOPE here, per the plan's design notes - the worksheet is the handoff, and the office
keys it into AutoCount by hand.

**Second amendment (captain, 21 Aug 00:40): the planner table.** `suggest` now answers two
further questions per line, both requested as a loading-plan-style table rather than the
first cut's flat checkbox list:

  * **Which PO covers this, earliest first.** `po_covered_qty` used to be one summed figure;
    it is now also broken down into `po_takes` - the per-PO quantities an EARLIEST-FIRST
    cascade would take, the identical discipline `project_order_inquiry_service._cascade_take`
    embodies for Place-on-PO (soonest `PurchaseOrderLine.expected_date`, then the PO's own
    number, then the line id) - COPIED here rather than imported, since that module is a large
    stateful class built around order-inquiry rows and importing it only for this one pure
    algorithm would drag its whole dependency graph into a module that has none of it (the
    same reasoning `_stock_context` above already gives for copying rather than importing
    `container_request_service`'s stock figures). The summed total is unchanged - a `need`
    (the packed qty) bigger than every candidate line combined still simply returns less than
    `need`, so `po_covered_qty` and `suggested_qty` read byte-identical to before this
    breakdown existed; only the per-PO detail is new.
  * **Which warehouse the SPO should land at.** `location_options` - one entry per candidate
    location carrying any live figure for this product (`location_stock_service.
    location_stock_for_product`, the SAME per-location reader the reorder Buy-row popup and
    the fulfilment board's `stock_detail` already use, so this screen's numbers can never
    disagree with theirs), each with its outstanding SO, on hand, and incoming SPO - the "after
    figure" (what `available` becomes once THIS SPO lands there) is left to the caller to add
    to whatever quantity it is proposing, since that quantity is edited live on screen and a
    server round-trip per keystroke would be the wrong shape for it. Ranked by the SAME
    Fulfilment Priority policy every other draw-down in this module uses
    (`priority.factors_for_demand_rows` - project earlier delivery first, then retail, never a
    second sort); `suggested_warehouse_id` is simply the top of that order. A product with no
    open demand or stock anywhere in the company (a first-time landing) falls back to the one
    "counts as available" warehouse (`allocation_suggestion_service._default_warehouse` -
    reused, not re-invented, for the identical reason that module already gives).

**One confirm, two writes - not a second approve step.** `create`'s `lines` payload gains an
optional `warehouse_id` per line. When present, the SAME action that mints the SPO also writes
the `spo_allocations` row for it (`SPOAllocationService.create_allocation`, the identical write
`allocation_suggestion_service.approve` uses) - so `scm.on_order_v` starts counting the new
supply at that warehouse the moment she presses Confirm, rather than a second screen. When
ABSENT (every caller before this amendment, and any line the buyer leaves unallocated), no
allocation is written for that line - `on_order_v` stays silent about it exactly as before,
which is the invariant `test_created_spo_lines_are_absent_from_on_order_v_until_allocated`
already locks in and this amendment does not disturb: allocation was always a decision, not a
default, and it still is - it is simply now a decision made on the SAME screen instead of a
second one, because the captain's plan for this table has her decide both there.

**Third amendment (captain live case, 21 Aug): delete the SPO, and self-heal a link that
outlives it.** He created SPOs from a draft shipment, then deleted their `spo_allocations` on
the SPO Allocations screen, and the planner tab stayed on "SPO already created" with no way
back - the SPO header and its `shipment_line_spo_link` row were both still there, only the
allocation was gone. Two moves:

  * `unwind` - the mirror of `create`. Deletes the `purchase_order_lines` + `purchase_orders`
    headers a shipment's `create` minted, the `shipment_line_spo_link` rows for the whole
    shipment, and any `spo_allocations` still hanging off those PO lines. Guarded twice: only
    `source_system == crm_spo` headers (an AutoCount import is refused, 409), and only headers
    linked to THIS shipment. Exposed on the planner as a Delete action on the already-converted
    state.
  * `_heal_stale_links` - `suggest`'s own defence against a CRM SPO removed by some path OTHER
    than `unwind` (a generic PO delete, a bad migration): a `shipment_line_spo_link` naming a
    PO/PO line that no longer exists is deleted on read, with a warning log, rather than
    trusted. A shipment left fully stale returns to `suggest`'s normal (non-converted) state; a
    shipment left partially stale (some SPOs deleted, some not) keeps `already_converted: true`
    and names only the SPOs still alive - `self_heal_note` says how many were cleared either
    way, non-null only when this run actually cleaned something up.

**Fourth amendment (captain, DB evidence, live case): the po_ref pin is supplier-scoped and
that defeats it.** PI line SRTWT7443 states po_ref `202605-S0060`, an open PO with 1,880 of
the product - but that PO is booked under the importer's name-squashed KAILU identity while
the shipment line itself carries the PI's own `400-J006` supplier code. `_po_cascade_lines`'s
pinned call ANDed `PurchaseOrder.supplier_id == supplier_id` onto the pin, so it returned
nothing and the planner read the line as covering 0 - exactly backwards from the module's own
rule, "a stated po_ref outranks inference". `_pinned_po_candidates` now resolves the STATED
number on its own (`po_number` is unique on `purchase_orders` in practice, so this is almost
always exactly one purchase order) and trusts it regardless of supplier spelling; the supplier
filter only comes back as a tiebreak on the rare/defensive case of more than one match. The
UN-pinned (product-match) path is unchanged - it still filters by supplier, because inference
with no stated document has nothing else to anchor it to.

**Fifth amendment (captain doctrine correction, 21 Aug): the arithmetic was inverted.** His own
words: "when there is PO, then we only can do SPO... it is when we got PO, then we only can
pull from the PO to form SPO." Every amendment above treated an open PO as competing supply
that REDUCED the suggested SPO qty (`packed - po_covered - on_hand - incoming_spo`). That is
backwards: an SPO is the SHIPMENT LEG of an existing PO, not a request that shrinks once a PO
happens to exist. Forming an SPO PULLS quantity FROM open PO lines; the pull IS the SPO's
composition, not a deduction from it.

  * **New arithmetic.** `suggested_qty` is now `po_covered_qty` itself - the SAME
    earliest-first `po_takes` cascade as before (soonest `expected_date`, then PO number),
    just no longer subtracted from anything. `_cascade_take`'s `need` argument is the packed
    qty, so the cascade still naturally caps at `min(packed, total pullable)` - the ARITHMETIC
    is unchanged, only what the caller DOES with the number is: it becomes the ask, not the
    remainder.
  * **On hand / incoming SPO drop out of the formula.** They stay on the response as CONTEXT
    (cheap - the same `_stock_context` query as before) but no longer net anything; a shipment
    with an open PO behind it is offered in full even while stock sits in the warehouse,
    because forming the SPO is about accounting for the PO, not about whether the goods are
    needed this minute.
  * **A packed quantity with no PO backing cannot become an SPO line.** `no_po_qty =
    max(packed - po_covered_qty, 0)` names the portion nothing open can back. When
    `po_covered_qty` is zero - nothing at all is pullable - the WHOLE line is `cannot_convert`
    (same shape as the no-supplier case, unselectable), reason `_REASON_NO_PO`: "No PO to pull
    from - raise the PO in AutoCount first." A PARTIALLY-backed line stays selectable at
    `po_covered_qty`; `no_po_qty` and a short note travel on `reason` so the shortfall is
    visible, never silently dropped.
  * **`covered` is gone.** It used to mean "nothing left to ask for, because a PO or stock
    already covers it" - a concept that only made sense when a PO was a deduction. There is no
    replacement flag: a line either has something pullable (`cannot_convert: false`,
    `suggested_qty = po_covered_qty`) or it does not (`cannot_convert: true`).

**Recording the pull, and the honesty question the plan asked to settle.** `create` decides,
per confirmed line, exactly which open PO line(s) the confirmed quantity draws down (the same
earliest-first cascade `suggest` already showed, re-run against LIVE data rather than trusted
from the earlier read - the standard "recompute at write time" rule every write path in this
module already follows). Two ways to record that pull were on the table:

  1. **Advance the source PO line's accounting** - `po_line.qty_received += take_qty` on every
     PO line a take draws from, the IDENTICAL write `allocation_suggestion_service.approve`
     already makes when a shipment draws down a PO line (see that module's own docstring:
     "the allocation raises `scm.on_order_v`; this makes `scm.po_ordered_v` fall"). Chosen.
  2. **Link only** - record which PO lines were touched and by how much, but leave their
     `qty_received` untouched, deferring the netting to the AutoCount book import that later
     reconciles this SPO by number.

  (1) is the honest one, and by a wide margin. Under (2), for as long as reconciliation has not
  happened - which is every day between "Create SPO" and the next AutoCount import, an interval
  this plan's own design notes already flag as open-ended - the SAME physical goods would count
  TWICE in `scm.po_ordered_v`: once as the original PO line's still-open balance, and again as
  the brand-new CRM SPO line's `qty_ordered`. Every screen that reads "ordered" (the PO book,
  the container request's own PO column, the reorder engine's outstanding-PO context) would
  overstate supply by exactly what "Create SPO" just did, silently, for however long
  reconciliation takes. (1) keeps the total byte-identical before and after: the source line's
  open balance falls by the take, the new SPO line's `qty_ordered` rises by the same take, nets
  to zero movement in the company-wide "ordered" total - the conversion re-attributes an
  existing order to its shipment, it does not conjure a second one.

  **How the pull is recorded, without a new table.** `shipment_line_spo_link` already carries a
  UNIQUE constraint on `inbound_shipment_line_id` (migration 406) - one row per shipment line,
  ever - so a shipment line that cascades across MORE than one PO line cannot get a second link
  row for its second source. Rather than a migration to lift that (out of scope for this pass,
  flagged below), the new CRM SPO's own `purchase_order_lines.source_ref` - a free `String`
  column, unused by any `crm_spo` line before this - now carries the take breakdown as JSON:
  `[{"po_line_id": ..., "qty": ...}, ...]`, one entry per source PO line the confirmed quantity
  drew from. This is what makes (1) SAFELY reversible: `unwind` parses it back and un-advances
  exactly what `create` advanced, per source line, before deleting the CRM SPO rows - without
  it, deleting a CRM SPO would have left the source PO permanently short by whatever it lent,
  a real loss with no SPO left to explain it. A dedicated per-take link table (queryable in SQL
  without parsing JSON) is the natural follow-up if this trail needs to be machine-readable
  from outside this module - noted, not built, here.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date as _date
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.inventory import Warehouse
from app.models.projects import Project
from app.models.sales_agent import SalesAgent
from app.models.scm import ProformaInvoiceLine, ProformaInvoiceShipmentLink, ShipmentLineSpoLink
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.supplier_scope import is_uuid as _is_uuid

logger = logging.getLogger(__name__)

#: The CRM-originated marker on `purchase_orders.source_system` / `purchase_order_lines.
#: source_system`. Distinct from every AutoCount import stamp (`scm_po_history`,
#: `scm_spo_history`, `scm_upload`) and from the reorder engine's own draft marker
#: (`scm_recommendation`) - see the module docstring for every consumer this was checked
#: against (`po_ordered_v`, `on_order_v`, `purchase_order_service._source_label`,
#: `outstanding_import_service`'s history guard).
SOURCE_SYSTEM = "crm_spo"

#: A CRM SPO counts as "ordered" the moment it exists (the module docstring) - so it is
#: created ACTIVE + OPEN, never a draft a later Confirm step would have to promote. Mirrors
#: `purchase_order_service._ON_ORDER_STATUSES` / `_OPEN_LINE_STATUS`.
_STATUS = "active"
_LINE_STATUS = "open"

#: `NumberingService` doc_type for the CRM SPO's own series, kept distinct from every
#: AutoCount pattern (`######-S####`, `SPO-####/##-####`) and from the CRM's own canonical
#: PO series (`PO-{year}/{month}-####`, `decision_service`) so an AutoCount import can never
#: collide with a number this module minted. Falls back to a random suffix when no numbering
#: rule is configured, same shape as `proforma_invoice_service._draft_shipment_number`.
_NUMBER_DOC_TYPE = "purchase_order_crm_spo"
_NUMBER_PREFIX = "CRM-SPO"

_REASON_NO_SUPPLIER = "No supplier recorded on this shipment line, so it cannot be added to an SPO."
_REASON_NOT_SELECTED = "Not selected."
#: The doctrine correction's own line, verbatim from the captain - a packed quantity nothing
#: open can back cannot become an SPO line at all, same shape as the no-supplier case.
_REASON_NO_PO = "No PO to pull from - raise the PO in AutoCount first."


def _uuid() -> str:
    return str(uuid.uuid4())


def _f(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _g(value: float) -> str:
    """Trim a quantity for a sentence - `12.0` reads `12`, `12.5` reads `12.5`."""
    return f"{value:g}"


def _shipment_or_404(db: Session, shipment_id: str) -> InboundShipment:
    if not _is_uuid(shipment_id):
        raise AppException(404, "Inbound shipment not found")
    row = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).one_or_none()
    if row is None:
        raise AppException(404, "Inbound shipment not found")
    return row


def _existing_links(db: Session, shipment_id: str) -> list[ShipmentLineSpoLink]:
    return (
        db.query(ShipmentLineSpoLink)
        .filter(ShipmentLineSpoLink.inbound_shipment_id == shipment_id)
        .all()
    )


def _existing_spos(db: Session, shipment_id: str) -> list[dict]:
    rows = (
        db.query(PurchaseOrder)
        .join(ShipmentLineSpoLink, ShipmentLineSpoLink.purchase_order_id == PurchaseOrder.id)
        .filter(ShipmentLineSpoLink.inbound_shipment_id == shipment_id)
        .distinct()
        .all()
    )
    return [
        {
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "supplier_id": str(po.supplier_id) if po.supplier_id else None,
            "supplier_name": po.supplier.supplier_name if po.supplier else None,
        }
        for po in rows
    ]


def _heal_stale_links(
    db: Session, shipment_id: str, links: list[ShipmentLineSpoLink]
) -> tuple[list[ShipmentLineSpoLink], int]:
    """Verify every MATCHED link still names a live PO/PO line, and self-heal the ones that do
    not (the captain's second ask, 21 Aug: allocations deleted elsewhere left the planner stuck
    on "SPO already created" with nothing behind it). A CRM SPO removed by any path other than
    `unwind` above - a generic PO delete, a bad migration - leaves `shipment_line_spo_link`
    behind: both FKs here are `ON DELETE SET NULL` (migration 406), so Postgres itself already
    clears `purchase_order_id` / `purchase_order_line_id` the moment the row they name is
    deleted, however that deletion happened. The tell is the COMBINATION this can only ever
    reach by that route: `unmatched_reason IS NULL` (so it was written as a MATCH, never a
    skip - every skip `create` writes always carries a reason) with `purchase_order_id IS NULL`
    (so whatever it matched is now gone). Trusting the row at face value is exactly what left
    the captain's planner stuck; this re-derives the truth from what Postgres already did to it
    rather than repeating that mistake. A `purchase_order_id` that is still present is
    re-queried for real (belt and braces against a schema where the delete path did not go
    through the FK at all), same for a lone orphaned `purchase_order_line_id` under a header
    that is otherwise still alive.

    Stale rows are DELETED here, on read, so the very next `suggest` answers honestly - back to
    its normal (non-`already_converted`) state when every link was stale, or naming only the
    SPOs still alive when some were (the partially-alive case: some SPOs deleted, some not).

    Returns the surviving links and how many were cleaned up, so the caller can say so.
    """
    candidates = [l for l in links if l.unmatched_reason is None]
    if not candidates:
        return links, 0

    po_ids = {str(l.purchase_order_id) for l in candidates if l.purchase_order_id}
    line_ids = {str(l.purchase_order_line_id) for l in candidates if l.purchase_order_line_id}
    live_po_ids = (
        {str(r[0]) for r in db.query(PurchaseOrder.id).filter(PurchaseOrder.id.in_(po_ids)).all()}
        if po_ids
        else set()
    )
    live_line_ids = (
        {
            str(r[0])
            for r in db.query(PurchaseOrderLine.id).filter(PurchaseOrderLine.id.in_(line_ids)).all()
        }
        if line_ids
        else set()
    )

    alive: list[ShipmentLineSpoLink] = []
    stale: list[ShipmentLineSpoLink] = []
    for link in links:
        if link.unmatched_reason is not None:
            alive.append(link)  # a genuine skip - nothing named, nothing to verify
            continue
        if link.purchase_order_id is None and link.purchase_order_line_id is None:
            # The SET-NULL signature: this was a MATCH (no reason) with nothing left to
            # name - its PO was deleted by some path other than `unwind`.
            stale.append(link)
            continue
        po_ok = link.purchase_order_id is None or str(link.purchase_order_id) in live_po_ids
        line_ok = link.purchase_order_line_id is None or str(link.purchase_order_line_id) in live_line_ids
        (alive if (po_ok and line_ok) else stale).append(link)

    if stale:
        logger.warning(
            "shipment_line_spo_link: %d stale row(s) for shipment %s point at a deleted "
            "purchase order/line - cleaning up on read",
            len(stale),
            shipment_id,
        )
        for link in stale:
            db.delete(link)
        db.flush()

    return alive, len(stale)


def _po_refs_for_line(db: Session, shipment_line_id: str) -> set[str]:
    """The `po_ref`(s) named on the PI line(s) this shipment line was drafted from, if any.

    A shipment line reached through the draft-from-PI convert can aggregate several PI
    lines (same product, same supplier, across invoices - `proforma_invoice_service`'s own
    grouping); a shipment reached from a real packing-list upload has none at all, and this
    returns empty for it.
    """
    rows = (
        db.query(ProformaInvoiceLine.po_ref)
        .join(
            ProformaInvoiceShipmentLink,
            ProformaInvoiceShipmentLink.proforma_invoice_line_id == ProformaInvoiceLine.id,
        )
        .filter(
            ProformaInvoiceShipmentLink.inbound_shipment_line_id == shipment_line_id,
            ProformaInvoiceLine.po_ref.isnot(None),
        )
        .all()
    )
    return {r[0].strip() for r in rows if r[0] and r[0].strip()}


def _cascade_take(
    lines: list[tuple[PurchaseOrderLine, PurchaseOrder, float]], need: float
) -> list[tuple[PurchaseOrderLine, PurchaseOrder, float]]:
    """Earliest-first cascade take - the SAME discipline `project_order_inquiry_service.
    _cascade_take` embodies for Place-on-PO: `min(open balance, still needed)` off each
    candidate in the order it is given, stopping once `need` is covered. `lines` is already
    sorted earliest-first by the caller (`_po_cascade_lines`); each item carries its own open
    quantity. A `need` bigger than every candidate combined simply returns less than `need` -
    the caller decides what an unfinished walk means (here, the SPO still asks for the rest)."""
    still = need
    takes: list[tuple[PurchaseOrderLine, PurchaseOrder, float]] = []
    for line, po, available in lines:
        if still <= 0:
            break
        take = min(available, still)
        if take > 0:
            takes.append((line, po, take))
            still -= take
    return takes


def _open_line_rows(q) -> list[tuple[PurchaseOrderLine, PurchaseOrder, float]]:
    """Shared tail of both cascade lookups below: oldest DOCUMENT first, then keep only the
    lines with real open balance.

    Ordered by the purchase order's own `issue_date` since the captain's Q8 ruling (26 Aug):
    the buyer draws down the order they raised first, and a line's expected date is when it
    is due, not when it was ordered. The two disagree routinely - a PO raised in January can
    be due after one raised in March - and the old ordering answered the wrong question,
    which is why "which PO covers this" read differently here than in the PO book.
    `order_date` is NOT the column: it does not exist on `purchase_orders`.
    """
    rows = q.order_by(
        PurchaseOrder.issue_date.asc().nulls_last(),
        PurchaseOrderLine.expected_date.asc().nulls_last(),
        PurchaseOrder.po_number.asc(),
        PurchaseOrderLine.id.asc(),
    ).all()
    out: list[tuple[PurchaseOrderLine, PurchaseOrder, float]] = []
    for line, po in rows:
        available = max(float(line.qty_ordered or 0) - float(line.qty_received or 0), 0.0)
        if available > 0:
            out.append((line, po, available))
    return out


def _po_cascade_lines(
    db: Session, supplier_id: str, product_id: str
) -> list[tuple[PurchaseOrderLine, PurchaseOrder, float]]:
    """Open PO lines to this supplier for this product, EARLIEST `expected_date` FIRST, then
    document sequence - `project_order_inquiry_service._candidates_for_row`'s own
    ordering, so a "which PO covers this" answer here can never disagree with what the
    Place-on-PO cascade would say about the same purchase order. The PRODUCT-match (inference)
    path only - a STATED po_ref is resolved by `_pinned_po_candidates` below, which does NOT
    filter by supplier (see that function's docstring for why the two paths diverge)."""
    q = (
        db.query(PurchaseOrderLine, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.notin_(("draft", "draft_recommendation")),
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.line_status == "open",
        )
    )
    return _open_line_rows(q)


def _pinned_po_candidates(
    db: Session, po_number: str, supplier_id: str, product_id: str
) -> list[tuple[PurchaseOrderLine, PurchaseOrder, float]]:
    """Resolve a STATED po_ref - the module's own rule, "a stated po_ref outranks inference" -
    WITHOUT filtering by supplier first (captain, DB evidence, live case): a PI's supplier name
    and the CRM book's supplier for the same factory can be spelled differently (an importer's
    name-squashed identity vs the PI's own code) - PI line SRTWT7443 states po_ref
    202605-S0060, an open PO with 1,880 of the product, booked under KAILU, while the shipment
    line itself carries supplier 400-J006. Filtering the PIN by supplier as well as by number
    defeated the pin in exactly the case it exists for, and the planner read the line as
    covering 0.

    `po_number` is UNIQUE on `purchase_orders` in practice, so this almost always resolves to
    exactly one purchase order - trust the stated document then, regardless of supplier
    spelling. If it somehow resolves to MORE than one (the schema does not forbid it even
    though the live data does), the supplier is the tiebreak: narrow to the match(es) that
    also agree with it, the same filter the inference path always applies.
    """
    matches = db.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_number).all()
    if len(matches) > 1:
        matches = [po for po in matches if str(po.supplier_id) == str(supplier_id)]
    po_ids = [po.id for po in matches]
    if not po_ids:
        return []
    q = (
        db.query(PurchaseOrderLine, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.purchase_order_id.in_(po_ids),
            PurchaseOrder.status.notin_(("draft", "draft_recommendation")),
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.line_status == "open",
        )
    )
    return _open_line_rows(q)


def _match_takes_for_line(
    db: Session, ln: InboundShipmentLine, need: float
) -> tuple[Optional[str], list[tuple[PurchaseOrderLine, PurchaseOrder, float]]]:
    """The one PO-matching decision this module makes, shared by `suggest` (a read against
    `need = packed`) and `create` (a FRESH read, at write time, against `need = the confirmed
    qty` - never the earlier `suggest` numbers, so a PO that moved between the two calls is
    never double-spent). Pin first (a stated `po_ref` outranks inference), fall back to a
    plain product/supplier match. Returns `(matched_by, takes)` - `takes` empty and
    `matched_by` `None` when nothing is pullable at all."""
    supplier_id = str(ln.supplier_id) if ln.supplier_id else None
    if supplier_id is None or need <= 0:
        return None, []

    po_refs = _po_refs_for_line(db, str(ln.id))
    matched_by: Optional[str] = None
    takes: list[tuple[PurchaseOrderLine, PurchaseOrder, float]] = []
    if len(po_refs) == 1:
        pinned_lines = _pinned_po_candidates(db, next(iter(po_refs)), supplier_id, str(ln.product_id))
        if pinned_lines:
            takes = _cascade_take(pinned_lines, need)
            matched_by = "po_ref"
    if matched_by is None:
        product_lines = _po_cascade_lines(db, supplier_id, str(ln.product_id))
        takes = _cascade_take(product_lines, need)
        if takes:
            matched_by = "product"
    return matched_by, takes


def _stock_context(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """On hand + incoming SPO, company-wide, per product - COPIED from
    `container_request_service._stock_context` rather than imported (same reasoning that
    module gives for copying `loading_plan_service._catalogue_cbm`: two lanes touching the
    same file is a worse cost than a few duplicated lines). Same figures, same views, so this
    screen and the container request can never disagree about what is on hand or incoming.

    CONTEXT ONLY since the doctrine correction (module docstring, fifth amendment) - neither
    figure feeds `suggested_qty` any more. Kept because it is cheap (one query, already paid
    for by every earlier version of this module) and still useful to see beside the ask."""
    if not product_ids:
        return {}
    prod_scope, prod_params = company_sql_predicate(db, "p.company_id", param_prefix="scp")
    wh_scope, wh_params = company_sql_predicate(db, "w.company_id", param_prefix="scw")
    where = ["np.product_id::text = ANY(:pids)"]
    if prod_scope:
        where.append(prod_scope)
    if wh_scope:
        where.append(wh_scope)
    sql = f"""
        SELECT np.product_id::text AS product_id,
               SUM(COALESCE(np.quantity_on_hand, 0)) AS on_hand,
               SUM(COALESCE(np.on_order, 0)) AS incoming_spo
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        WHERE {' AND '.join(where)}
        GROUP BY np.product_id
    """
    rows = db.execute(
        text(sql), {"pids": product_ids, **prod_params, **wh_params}
    ).mappings().all()
    return {
        r["product_id"]: {
            "on_hand": float(r["on_hand"] or 0),
            "incoming_spo": float(r["incoming_spo"] or 0),
        }
        for r in rows
    }


def _demand_by_warehouse(db: Session, product_id: str) -> dict[str, dict]:
    """Per-warehouse open-SO demand shape for ONE product - the same predicate
    `location_stock_service.location_stock_for_product`'s own `so_qty` aggregate uses
    (`SalesOrder.status == 'open'`, `demand.is_open_demand()`), grouped further by earliest
    need-by date, oldest document date and demand class so `_location_options` can rank
    candidate locations through the shared Fulfilment Priority policy instead of a private
    sort. Class follows the repo's own rule (not a literal match): a warehouse with ANY
    project-class line ranks as project (project need is what the plan cares about seeing
    first), else retail when any line names a class, else unclassified.

    `payment_terms_days` is sourced the SAME way the auto-place ranking already does
    (`priority.payment_terms_by_customer`, `project_supply_service`/`project_fulfilment_board
    _service`'s own reads) rather than left hard-coded absent: every customer with open demand
    behind this warehouse is looked up, and the SHORTEST of their terms is kept - the same
    "shorter is higher" reading `priority.factors_for_demand_rows` gives the `customer_credit`
    factor generally, applied here at the location's most credit-sensitive customer. None
    (ABSENT, never a false best/worst) when nobody behind this location has been assessed."""
    from app.services.scm import priority
    from app.services.scm.demand import is_open_demand

    rows = (
        db.query(
            SalesOrderLine.warehouse_id,
            func.min(SalesOrderLine.required_date).label("required_date"),
            func.min(SalesOrder.order_date).label("order_date"),
            func.bool_or(SalesOrder.demand_class == "project").label("has_project"),
            func.bool_or(
                SalesOrder.demand_class.isnot(None) & (SalesOrder.demand_class != "project")
            ).label("has_retail"),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id == product_id,
            SalesOrder.status == "open",
            is_open_demand(),
            SalesOrderLine.warehouse_id.isnot(None),
        )
        .group_by(SalesOrderLine.warehouse_id)
        .all()
    )
    if not rows:
        return {}

    customer_pairs = (
        db.query(SalesOrderLine.warehouse_id, SalesOrder.customer_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id == product_id,
            SalesOrder.status == "open",
            is_open_demand(),
            SalesOrderLine.warehouse_id.isnot(None),
            SalesOrder.customer_id.isnot(None),
        )
        .distinct()
        .all()
    )
    customers_by_warehouse: dict[str, set[str]] = {}
    for wh_id, cust_id in customer_pairs:
        customers_by_warehouse.setdefault(str(wh_id), set()).add(str(cust_id))
    all_customer_ids = {cid for ids in customers_by_warehouse.values() for cid in ids}
    terms_by_customer = priority.payment_terms_by_customer(db, list(all_customer_ids))

    out: dict[str, dict] = {}
    for r in rows:
        klass = "project" if r.has_project else "retail" if r.has_retail else None
        wh_key = str(r.warehouse_id)
        terms_here = [
            terms_by_customer[cid]
            for cid in customers_by_warehouse.get(wh_key, ())
            if terms_by_customer.get(cid) is not None
        ]
        out[wh_key] = {
            "required_date": r.required_date,
            "order_date": r.order_date,
            "demand_class": klass,
            "payment_terms_days": min(terms_here) if terms_here else None,
        }
    return out


def _demand_lines_by_warehouse(db: Session, product_id: str) -> dict[str, list[dict]]:
    """The INDIVIDUAL open SO lines behind `_demand_by_warehouse`'s aggregates - the doctrine
    correction's second drill: "what SO am I covering", per candidate location, earliest need
    date first. Same predicate `location_stock_for_product`'s own `so_qty` aggregate uses
    (`SalesOrder.status == 'open'`, `demand.is_open_demand()`); read once per product rather
    than once per candidate location. `agent_name` is a cheap outer join (`sales_agents`
    already carries a plain name column) - absent, never fabricated, on a line with no agent
    on file.

    Deliberately NOT cascaded/capped against the SPO qty here - a location's demand list is
    the same regardless of how much of it this particular SPO ends up satisfying, and the
    qty being proposed is edited live on screen (the same reason `_location_options.available`
    leaves its own "after figure" to the caller). The FE runs the identical earliest-first
    cascade against these rows and the live qty to answer "which of these does THIS SPO cover"
    and to bucket the SO-coverage schedule matrix - mirroring `po_takes`, computed the same way
    just on the other side of the shipment.
    """
    from app.services.scm.demand import demand_qty, is_open_demand

    owed = demand_qty()
    rows = (
        db.query(
            SalesOrderLine.warehouse_id,
            SalesOrder.so_number,
            Customer.customer_name,
            SalesAgent.sales_agent,
            SalesOrderLine.required_date,
            SalesOrder.order_date,
            owed.label("qty"),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
        .filter(
            SalesOrderLine.product_id == product_id,
            SalesOrder.status == "open",
            is_open_demand(),
            SalesOrderLine.warehouse_id.isnot(None),
        )
        .order_by(
            SalesOrderLine.required_date.asc().nulls_last(),
            SalesOrder.order_date.asc().nulls_last(),
            SalesOrder.so_number.asc(),
        )
        .all()
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r.warehouse_id), []).append({
            "so_number": r.so_number,
            "customer_name": r.customer_name,
            "agent_name": r.sales_agent,
            "required_date": r.required_date.isoformat() if r.required_date else None,
            "order_date": r.order_date.isoformat() if r.order_date else None,
            "qty": float(r.qty or 0),
        })
    return out


#: How a ticked piece of demand is named on the wire, and what the create sends back.
#: `project:<order inquiry row id>` / `retail:<sales order line id>` - the family is part of
#: the key because the two are different records, and only one of them can carry a link.
_COVERAGE_PROJECT = "project"
_COVERAGE_RETAIL = "retail"


def _project_coverage(db: Session, product_id: str) -> list[dict]:
    """Unlinked project demand for this product - the order-inquiry rows (R1, part 2 P3).

    Only ORDER BACK rows: an ORDER is a new purchase and goes on a purchase order, and
    `project_order_inquiry_service` refuses an SPO link on any other verb - so offering one
    here would offer a tick that cannot be honoured.

    `qty` is what the row still needs, net of every link it already carries. A row half
    placed on a purchase order is offered for the other half, and a fully placed row is not
    offered at all.
    """
    from app.models.project_so import (
        INQUIRY_CANCELLED,
        IV_ORDER_BACK,
        OrderInquiry,
        OrderInquiryLink,
        OrderInquiryRow,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
    )

    rows = (
        db.query(
            OrderInquiryRow,
            ProjectSalesOrder.autocount_doc_no,
            ProjectSalesOrder.provisional_ref,
            Project.title,
        )
        .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .join(ProjectSalesOrder, ProjectSalesOrder.id == OrderInquiry.project_sales_order_id)
        .outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
        .filter(
            ProjectSalesOrderLine.product_id == product_id,
            OrderInquiryRow.verb == IV_ORDER_BACK,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(
            OrderInquiryRow.delivery_date.asc().nulls_last(),
            OrderInquiryRow.id.asc(),
        )
        .all()
    )
    if not rows:
        return []

    linked: dict[str, float] = {}
    for row_id, total in (
        db.query(OrderInquiryLink.row_id, func.sum(OrderInquiryLink.qty))
        .filter(OrderInquiryLink.row_id.in_([str(r.OrderInquiryRow.id) for r in rows]))
        .group_by(OrderInquiryLink.row_id)
        .all()
    ):
        linked[str(row_id)] = float(total or 0)

    codes = _warehouse_ids_by_code(db)
    out: list[dict] = []
    for row, doc_no, provisional, project_title in rows:
        need = float(row.qty or 0) - linked.get(str(row.id), 0.0)
        if need <= 0:
            continue
        location = (row.stock_location or "").strip().upper() or None
        warehouse_id = codes.get(location) if location else None
        out.append({
            "key": f"{_COVERAGE_PROJECT}:{row.id}",
            "kind": _COVERAGE_PROJECT,
            "document": doc_no or provisional,
            "customer_name": project_title,
            "required_date": row.delivery_date.isoformat() if row.delivery_date else None,
            "qty": need,
            "warehouse_id": warehouse_id,
            "warehouse_code": location,
        })
    return out


def _warehouse_ids_by_code(db: Session) -> dict[str, str]:
    """`{WAREHOUSE CODE: id}`. An inquiry row names its location as a CODE, and the split
    needs an id; a code naming no warehouse we hold simply steers nothing."""
    return {
        (code or "").strip().upper(): str(wid)
        for wid, code in db.query(Warehouse.id, Warehouse.warehouse_code).all()
        if code
    }


def _retail_coverage(db: Session, product_id: str) -> list[dict]:
    """Open sales-order book demand for this product - the retail half of the tick list.

    The same predicate `_demand_lines_by_warehouse` uses, so the two answers cannot
    disagree; the difference is that this one carries the LINE, because a tick has to name
    the thing it ticked.
    """
    from app.services.scm.demand import demand_qty, is_open_demand

    owed = demand_qty()
    rows = (
        db.query(
            SalesOrderLine.id,
            SalesOrderLine.warehouse_id,
            Warehouse.warehouse_code,
            SalesOrder.so_number,
            Customer.customer_name,
            SalesOrderLine.required_date,
            owed.label("qty"),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrderLine.product_id == product_id,
            SalesOrder.status == "open",
            is_open_demand(),
        )
        .order_by(
            SalesOrderLine.required_date.asc().nulls_last(),
            SalesOrder.so_number.asc(),
            SalesOrderLine.id.asc(),
        )
        .all()
    )
    return [
        {
            "key": f"{_COVERAGE_RETAIL}:{r.id}",
            "kind": _COVERAGE_RETAIL,
            "document": r.so_number,
            "customer_name": r.customer_name,
            "required_date": r.required_date.isoformat() if r.required_date else None,
            "qty": float(r.qty or 0),
            "warehouse_id": str(r.warehouse_id) if r.warehouse_id else None,
            "warehouse_code": r.warehouse_code,
        }
        for r in rows
        if float(r.qty or 0) > 0
    ]


def _so_coverage(db: Session, product_id: str, packed: float) -> list[dict]:
    """What this SPO could be for, and what the default ticks claim (Q4, AC-G3).

    Project by need-by date, THEN retail by need-by date - the priority policy's own order,
    stated here as a walk rather than a score because the operator is being asked to confirm
    a list, not to read a ranking. Ticks run down that list until the packed quantity is used
    up; everything after that is offered unticked, and what no tick claims is free stock
    (the "Unassigned" remainder the screen names).
    """
    coverage = _project_coverage(db, product_id) + _retail_coverage(db, product_id)
    left = packed
    for entry in coverage:
        take = min(entry["qty"], left) if left > 0 else 0.0
        entry["default_ticked"] = take > 0
        left -= take
    return coverage


def _location_options(db: Session, product_id: str) -> dict:
    """Candidate destination warehouses for a new SPO on this product, ranked - the module
    docstring's "second amendment" section. Every location carrying any live figure for the
    product (`location_stock_service.location_stock_for_product` - the SAME per-location
    reader the reorder Buy-row popup and the fulfilment board already use), ranked by the
    active Fulfilment Priority policy (`priority.factors_for_demand_rows` - project earlier
    delivery first, then retail, never a second sort); a location with no open demand behind
    it sorts after every ranked one, by warehouse code, mirroring `container_request_service.
    build`'s own "ranked rows, then no-demand rows" order. A product with nothing anywhere
    (never sold or stocked) falls back to the one "counts as available" warehouse
    (`allocation_suggestion_service._default_warehouse`, reused rather than reinvented)."""
    from app.services.scm import priority
    from app.services.scm.allocation_suggestion_service import _default_warehouse
    from app.services.scm.location_stock_service import location_stock_for_product

    locations = location_stock_for_product(db, product_id).get("locations", [])
    if not locations:
        fallback = _default_warehouse(db)
        if not fallback:
            return {"options": [], "suggested_warehouse_id": None}
        return {
            "options": [
                {
                    "warehouse_id": str(fallback["id"]),
                    "warehouse_code": fallback["warehouse_code"],
                    "outstanding_so": 0.0,
                    "on_hand": 0.0,
                    "incoming_spo": 0.0,
                    "available": 0.0,
                    "rank_score": None,
                    "demand_lines": [],
                }
            ],
            "suggested_warehouse_id": str(fallback["id"]),
        }

    demand = _demand_by_warehouse(db, product_id)
    demand_lines = _demand_lines_by_warehouse(db, product_id)
    demand_rows = [
        {
            "row_key": loc["warehouse_id"],
            "required_date": demand[loc["warehouse_id"]]["required_date"],
            "order_date": demand[loc["warehouse_id"]]["order_date"],
            "payment_terms_days": demand[loc["warehouse_id"]]["payment_terms_days"],
            "demand_class": demand[loc["warehouse_id"]]["demand_class"],
        }
        for loc in locations
        if loc["warehouse_id"] in demand
    ]
    scores: dict[str, float] = {}
    if demand_rows:
        factors_by_row = priority.factors_for_demand_rows(db, demand_rows)
        scores = priority.scores_for(factors_by_row)

    options = [
        {
            "warehouse_id": loc["warehouse_id"],
            "warehouse_code": loc["warehouse_code"],
            "outstanding_so": loc["so_qty"],
            "on_hand": loc["on_hand"],
            "incoming_spo": loc["spo_qty"],
            # Signed, never clamped - same rule `location_stock_for_product`'s own
            # `available` already carries. The caller adds whatever qty it proposes landing
            # here to get the "after figure" the plan asks for - computed against the LIVE,
            # edited quantity on screen, never a value this endpoint would have to go stale.
            "available": loc["available"],
            "rank_score": scores.get(loc["warehouse_id"]),
            # "What SO am I covering" - the individual demand lines behind `outstanding_so`,
            # earliest need date first. The FE cascades these against its own live SPO qty
            # (and its own per-location split) to answer which of them this SPO actually
            # serves, and to bucket the SO-coverage schedule matrix.
            "demand_lines": demand_lines.get(loc["warehouse_id"], []),
        }
        for loc in locations
    ]
    options.sort(
        key=lambda o: (
            0 if o["rank_score"] is not None else 1,
            -(o["rank_score"] or 0.0),
            o["warehouse_code"] or "",
        )
    )
    suggested = options[0]["warehouse_id"] if options else None
    return {"options": options, "suggested_warehouse_id": suggested}


def suggest(db: Session, shipment_id: str) -> dict:
    """What "Create SPO" would ask for, per shipment line - the DOCTRINE-CORRECTED arithmetic
    (module docstring, fifth amendment): `suggested_qty` is what an open PO PULLS this SPO up
    to, not what is left after a PO is subtracted. Almost a pure read - the one exception is
    `_heal_stale_links`, which deletes any link row a prior `create` wrote that no longer
    points at a live PO/PO line (see that function's docstring). The caller must `db.commit()`
    after this, same as every other lazily-self-healing GET in this codebase (`explainer.py`'s
    cached-explanation routes)."""
    shipment = _shipment_or_404(db, shipment_id)
    lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    )

    already, healed_count = _heal_stale_links(db, shipment.id, _existing_links(db, shipment.id))
    self_heal_note = (
        f"{healed_count} SPO{'s' if healed_count != 1 else ''} previously linked to this "
        "shipment no longer exist and have been cleared - Create SPO can be run again for them."
        if healed_count
        else None
    )
    if already:
        return {
            "shipment_id": str(shipment.id),
            "shipment_number": shipment.shipment_number,
            "shipment_status": shipment.shipment_status,
            "already_converted": True,
            "existing_spos": _existing_spos(db, shipment.id),
            "lines": [],
            "self_heal_note": self_heal_note,
        }

    product_ids = [str(ln.product_id) for ln in lines if ln.product_id]
    supplier_ids = {str(ln.supplier_id) for ln in lines if ln.supplier_id}
    products = {
        str(pid): (code, name)
        for pid, code, name in db.query(*_product_cols()).filter(_product_id_in(product_ids)).all()
    } if product_ids else {}
    suppliers = (
        {str(s.id): s.supplier_name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
        if supplier_ids
        else {}
    )
    stock = _stock_context(db, product_ids)
    # One `_location_options` call per DISTINCT product on the shipment, not per line - two
    # shipment lines of the same product (different suppliers, say) ask the same "where does
    # this land" question and must get the same ranked answer.
    location_cache: dict[str, dict] = {}

    out_lines: list[dict] = []
    for ln in sorted(lines, key=lambda l: (products.get(str(l.product_id), (None, None))[0] or "", str(l.id))):
        packed = float(ln.quantity_shipped or 0)
        product = products.get(str(ln.product_id))
        item_code, product_name = product if product else (None, None)
        supplier_id = str(ln.supplier_id) if ln.supplier_id else None

        if supplier_id is None:
            out_lines.append({
                "shipment_line_id": str(ln.id),
                "product_id": str(ln.product_id),
                "item_code": item_code,
                "product_name": product_name,
                "supplier_id": None,
                "supplier_name": None,
                "packed_qty": packed,
                "po_covered_qty": 0.0,
                "matched_po_number": None,
                "matched_by": None,
                "po_takes": [],
                "on_hand": 0.0,
                "incoming_spo": 0.0,
                "suggested_qty": 0.0,
                "no_po_qty": packed,
                "cannot_convert": True,
                "reason": _REASON_NO_SUPPLIER,
                "unit_cost": _f(ln.unit_cost),
                "currency": ln.currency,
                "location_options": [],
                "suggested_warehouse_id": None,
                "so_coverage": [],
            })
            continue

        matched_by, takes = _match_takes_for_line(db, ln, packed)
        po_covered = sum(t[2] for t in takes)
        matched_po_number = takes[0][1].po_number if takes else None
        po_takes = [
            {
                "po_line_id": str(line.id),
                "po_number": po.po_number,
                "qty": qty,
                "expected_date": line.expected_date.isoformat() if line.expected_date else None,
                # The captain's own ask (doctrine correction, per-take drill): the PO's OWN
                # date and supplier, not just its number - a pinned match can resolve to a
                # PO booked under a differently-spelled supplier (fourth amendment), so this
                # is the PO's supplier, not necessarily the shipment line's.
                "po_date": po.issue_date.isoformat() if po.issue_date else None,
                "supplier_name": po.supplier.supplier_name if po.supplier else None,
            }
            for line, po, qty in takes
        ]

        # The doctrine correction's own arithmetic (module docstring, fifth amendment):
        # `suggested_qty` IS `po_covered_qty` - what an open PO pulls this SPO up to, never a
        # remainder after PO/stock is subtracted. `on_hand` / `incoming_spo` stay on the
        # response as context only.
        suggested = po_covered
        no_po_qty = max(packed - po_covered, 0.0)
        cannot_convert = po_covered <= 0
        if cannot_convert:
            reason = _REASON_NO_PO
        elif no_po_qty > 0:
            reason = (
                f"{_g(no_po_qty)} of {_g(packed)} has no PO to pull from - raise it in "
                "AutoCount first."
            )
        else:
            reason = None

        ctx = stock.get(str(ln.product_id), {"on_hand": 0.0, "incoming_spo": 0.0})

        # No point ranking a destination for a line that cannot become an SPO line at all -
        # mirrors the no-supplier branch above, which never fetches locations either.
        location = {"options": [], "suggested_warehouse_id": None}
        if not cannot_convert:
            pid = str(ln.product_id)
            if pid not in location_cache:
                location_cache[pid] = _location_options(db, pid)
            location = location_cache[pid]

        out_lines.append({
            "shipment_line_id": str(ln.id),
            "product_id": str(ln.product_id),
            "item_code": item_code,
            "product_name": product_name,
            "supplier_id": supplier_id,
            "supplier_name": suppliers.get(supplier_id),
            "packed_qty": packed,
            "po_covered_qty": po_covered,
            "matched_po_number": matched_po_number,
            "matched_by": matched_by,
            "po_takes": po_takes,
            "on_hand": ctx["on_hand"],
            "incoming_spo": ctx["incoming_spo"],
            "suggested_qty": suggested,
            "no_po_qty": no_po_qty,
            "cannot_convert": cannot_convert,
            "reason": reason,
            "unit_cost": _f(ln.unit_cost),
            "currency": ln.currency,
            "location_options": location["options"],
            "suggested_warehouse_id": location["suggested_warehouse_id"],
            # What this SPO could be FOR, with the default ticks already walked (AC-G3).
            # Empty on a line that cannot convert - there is nothing to point anywhere.
            "so_coverage": [] if cannot_convert else _so_coverage(db, str(ln.product_id), packed),
        })

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "shipment_status": shipment.shipment_status,
        "already_converted": False,
        "existing_spos": [],
        "lines": out_lines,
        "self_heal_note": self_heal_note,
    }


def _product_cols():
    from app.models.product import Product

    return (Product.id, Product.product_code, Product.product_name)


def _product_id_in(ids: list[str]):
    from app.models.product import Product

    return Product.id.in_(ids)


def _spo_number(db: Session) -> str:
    number = NumberingService(db).get_next_number(_NUMBER_DOC_TYPE, _date.today(), commit_rule=False)
    return number or f"{_NUMBER_PREFIX}-{uuid.uuid4().hex[:8]}"


def create(
    db: Session,
    shipment_id: str,
    lines: list[dict],
    *,
    actor: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> dict:
    """Confirm the screen `suggest` drew. One `purchase_orders` header per supplier, each new
    line PULLING its confirmed quantity from open PO line(s) - the doctrine correction (module
    docstring, fifth amendment), re-derived HERE against live data rather than trusted from
    `suggest`'s earlier read, the same "recompute at write time" rule every write in this
    module already follows.

    `lines` is `[{shipment_line_id, qty, include, location_splits}]` - every shipment line, per
    the "same structure on read and write" screen shape: a line the buyer left unticked still
    needs a row here so the whole shipment is accounted for in ONE action, not a part of it
    silently left for later. A line whose `qty` cannot be backed by ANY open PO (fresh check,
    not the `suggest` snapshot) is skipped with `_REASON_NO_PO`, same as an untouched line is
    skipped `_REASON_NOT_SELECTED` - "not selectable" holds at write time too, not only on the
    read that drew the screen.

    `location_splits` (fourth ask, multi-location) is OPTIONAL and, when present, a list of
    `{warehouse_id, qty}` that must sum to EXACTLY what this line actually pulls (recomputed,
    not the client's stated `qty`) - the same "a split must add up" hard rule `allocation_
    suggestion_service.approve` already enforces for its own splits, applied here because this
    screen now makes the identical kind of decision. Each split writes its own `spo_allocations`
    row in the SAME action that mints the SPO line - one confirm, still one write per DECISION,
    now zero-or-many decisions per line rather than zero-or-one. Absent/empty means no
    allocation is written for that line, byte-identical to a line with no location chosen -
    `scm.on_order_v` stays silent about it until someone allocates it.
    `actor_user_id` is the real user id `spo_allocations.created_by` needs (a UUID column);
    `actor`, kept as-is, is the human-readable name other provenance on this shipment stamps.
    """
    shipment = _shipment_or_404(db, shipment_id)

    if _existing_links(db, shipment.id):
        existing = _existing_spos(db, shipment.id)
        names = ", ".join(sorted({s["po_number"] or "?" for s in existing}))
        raise AppException(
            409,
            f"An SPO has already been created from this shipment: {names}.",
            detail="already_converted",
        )

    shipment_lines = {
        str(ln.id): ln
        for ln in db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    }
    if not shipment_lines:
        raise AppException(422, "This shipment has no lines to create an SPO from.")

    by_line = {str(item.get("shipment_line_id") or ""): item for item in (lines or [])}
    missing = [lid for lid in shipment_lines if lid not in by_line]
    if missing:
        raise AppException(
            422,
            "Every line on this shipment must be accounted for.",
            detail=f"{len(missing)} line(s) missing from the request",
        )

    groups: dict[str, dict[str, Any]] = {}
    skipped: list[tuple[str, str]] = []
    ticked_demand: dict[str, list[str]] = {}

    for line_id, ln in shipment_lines.items():
        item = by_line[line_id]
        include = bool(item.get("include"))
        requested = float(item.get("qty") or 0)
        splits = [
            {"warehouse_id": str(s.get("warehouse_id") or ""), "qty": float(s.get("qty") or 0)}
            for s in (item.get("location_splits") or [])
            if s.get("warehouse_id")
        ]
        supplier_id = str(ln.supplier_id) if ln.supplier_id else None

        if supplier_id is None:
            skipped.append((line_id, _REASON_NO_SUPPLIER))
            continue
        if not include or requested <= 0:
            skipped.append((line_id, _REASON_NOT_SELECTED))
            continue

        # Re-derive what is ACTUALLY pullable right now - never the qty the client sent, and
        # never `suggest`'s earlier read: a PO another confirm consumed in between must not be
        # double-spent. Capped at what shipped, and at what the buyer asked for.
        need = min(requested, float(ln.quantity_shipped or 0))
        matched_by, takes = _match_takes_for_line(db, ln, need)
        # Only the takes the buyer left ticked (AC-G1). ABSENT means "every take you
        # re-derive", which is what every caller before this ask sent; an empty LIST means
        # "draw from none of them", and a line drawing from nothing cannot become an SPO
        # line - the same outcome as having no open PO at all.
        take_ids = item.get("po_take_ids")
        if take_ids is not None:
            wanted = {str(t) for t in take_ids}
            takes = [t for t in takes if str(t[0].id) in wanted]
        covered_now = sum(t[2] for t in takes)
        if covered_now <= 0:
            skipped.append((line_id, _REASON_NO_PO))
            continue

        if splits:
            split_total = sum(s["qty"] for s in splits)
            if abs(split_total - covered_now) > 1e-6:
                raise AppException(
                    422,
                    "A line's location split has to add up to its SPO qty.",
                    detail=f"{_g(split_total)} split against {_g(covered_now)} pulled from PO.",
                )

        group = groups.setdefault(
            supplier_id,
            {"lines": [], "currency": ln.currency},
        )
        group["lines"].append((ln, covered_now, takes, splits))
        # Which demand this line's quantity was ticked against (AC-G3). Held per shipment
        # line so the links can be written AFTER the allocations exist to point at.
        ticked_demand[line_id] = [str(k) for k in (item.get("so_line_ids") or [])]

    if not groups:
        raise AppException(
            422,
            "Nothing was selected to create an SPO from.",
            detail="nothing_selected",
        )

    supplier_names = {
        str(s.id): s.supplier_name
        for s in db.query(Supplier).filter(Supplier.id.in_(list(groups.keys()))).all()
    }

    created_spos: list[dict] = []
    line_links: dict[str, tuple[str, str]] = {}  # shipment_line_id -> (po_id, po_line_id)
    # One entry per location split, across every line - read after every SPO/line/link row
    # above is written, so an allocation is never attempted against a purchase-order line
    # that does not exist yet.
    allocation_targets: list[dict[str, Any]] = []

    for supplier_id, group in groups.items():
        po = PurchaseOrder(
            id=_uuid(),
            po_number=_spo_number(db),
            supplier_id=supplier_id,
            issue_date=_date.today(),
            expected_date=shipment.eta_delay_date or shipment.estimated_arrival_date,
            status=_STATUS,
            currency=group["currency"],
            source_system=SOURCE_SYSTEM,
            source_ref=str(shipment.id),
        )
        db.add(po)
        db.flush()

        total_qty = 0.0
        for ln, covered_now, takes, splits in group["lines"]:
            po_line = PurchaseOrderLine(
                id=_uuid(),
                purchase_order_id=po.id,
                product_id=ln.product_id,
                qty_ordered=Decimal(str(covered_now)),
                qty_received=0,
                unit_cost=ln.unit_cost,
                currency=ln.currency,
                expected_date=po.expected_date,
                line_status=_LINE_STATUS,
                source_system=SOURCE_SYSTEM,
                # WHICH open PO line(s) this pull drew from, and how much of each - see the
                # module docstring's fifth amendment for why this is JSON on `source_ref`
                # rather than a new link table. Replaces the shipment-line-id this column
                # used to carry (redundant - `ShipmentLineSpoLink.inbound_shipment_line_id`
                # already names it).
                source_ref=json.dumps([
                    {"po_line_id": str(src_line.id), "qty": qty}
                    for src_line, _src_po, qty in takes
                ]),
            )
            db.add(po_line)
            db.flush()
            line_links[str(ln.id)] = (po.id, po_line.id)

            # The pull ADVANCES the source PO line's own accounting - the honest choice the
            # module docstring works through (fifth amendment): the same write `allocation_
            # suggestion_service.approve` makes when a shipment draws down a PO line, so the
            # source line's open balance falls by exactly what this SPO line just claimed and
            # the company-wide "ordered" total nets to zero movement, never a double count.
            for src_line, _src_po, qty in takes:
                src_line.qty_received = float(src_line.qty_received or 0) + qty

            for split in splits:
                allocation_targets.append({
                    "shipment_line_id": str(ln.id),
                    "product_id": str(ln.product_id),
                    "warehouse_id": split["warehouse_id"],
                    "qty": split["qty"],
                    "po_number": po.po_number,
                    "po_line_id": po_line.id,
                })
            total_qty += covered_now

        created_spos.append({
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "supplier_id": supplier_id,
            "supplier_name": supplier_names.get(supplier_id),
            "currency": po.currency,
            "lines": len(group["lines"]),
            "qty": total_qty,
        })

    for line_id, (po_id, po_line_id) in line_links.items():
        db.add(ShipmentLineSpoLink(
            id=_uuid(),
            inbound_shipment_id=shipment.id,
            inbound_shipment_line_id=line_id,
            purchase_order_id=po_id,
            purchase_order_line_id=po_line_id,
        ))
    for line_id, reason in skipped:
        db.add(ShipmentLineSpoLink(
            id=_uuid(),
            inbound_shipment_id=shipment.id,
            inbound_shipment_line_id=line_id,
            purchase_order_id=None,
            purchase_order_line_id=None,
            unmatched_reason=reason,
        ))
    db.flush()

    allocations = _write_allocations(db, shipment, allocation_targets, actor_user_id=actor_user_id)
    demand_links = _link_ticked_demand(
        db, allocations, ticked_demand, actor_user_id=actor_user_id
    )

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "created_spos": created_spos,
        "demand_links": demand_links,
        "skipped": [
            {
                "shipment_line_id": lid,
                "item_code": None,
                "reason": reason,
            }
            for lid, reason in skipped
        ],
        "allocations": allocations,
    }


def _write_allocations(
    db: Session,
    shipment: InboundShipment,
    targets: list[dict[str, Any]],
    *,
    actor_user_id: Optional[str],
) -> list[dict]:
    """The second half of "one confirm, two writes" - `SPOAllocationService.create_allocation`,
    the IDENTICAL write `allocation_suggestion_service.approve` uses, so this action and that
    one can never disagree about what an allocation is. `forward_match=False` per row and one
    sweep per distinct SPO number at the end, for the exact reason `approve` already gives:
    several warehouses can share one SPO number here (a container is routinely several
    factories, several destinations - and, since the fourth ask, several destinations for ONE
    factory's line too), and firing the GRN-forward-match hook per row would place a waiting
    GRN line before every allocation under that number exists.

    `targets` is a FLAT list, one entry per location split - a line with two splits writes two
    allocations here, both against the SAME `po_line_id` (its one new SPO line)."""
    if not targets:
        return []
    from app.schemas.procurement import SPOAllocationCreate
    from app.services.grn_spo_matching import forward_match_grn_lines_for_spo_best_effort
    from app.services.procurement_service import SPOAllocationService

    service = SPOAllocationService(db)
    written: list[dict] = []
    forward_match_targets: set[tuple[str, Optional[str]]] = set()
    for target in targets:
        allocation = service.create_allocation(
            SPOAllocationCreate(
                spo_number=target["po_number"],
                inbound_shipment_id=str(shipment.id),
                product_id=target["product_id"],
                warehouse_id=target["warehouse_id"],
                allocated_quantity=int(round(target["qty"])),
                po_line_id=target["po_line_id"],
            ),
            created_by=actor_user_id,
            forward_match=False,
        )
        written.append({
            "shipment_line_id": target["shipment_line_id"],
            "warehouse_id": target["warehouse_id"],
            "allocation_id": str(allocation.id),
            "qty": target["qty"],
        })
        forward_match_targets.add((
            target["po_number"],
            str(allocation.company_id) if allocation.company_id is not None else None,
        ))

    for spo_number, company_id in forward_match_targets:
        forward_match_grn_lines_for_spo_best_effort(db, spo_number, company_id=company_id)

    return written


def _link_ticked_demand(
    db: Session,
    allocations: list[dict],
    ticked: dict[str, list[str]],
    *,
    actor_user_id: Optional[str],
) -> list[dict]:
    """Tie the ticked PROJECT demand to the SPO allocations that will serve it (AC-G6).

    Written through `ProjectOrderInquiryService.place_on_po_allocations`, the ONE writer of
    `projects.order_inquiry_links` (part 2 I), rather than inserting the row here: that
    service holds the rules a link has to obey - the row is never split, the target must
    still be open for that product, an SPO answers only an ORDER BACK row - and a second
    writer would be a second, quietly different set of them.

    **A RETAIL tick writes no link, by design.** `order_inquiry_links.row_id` is NOT NULL:
    the table hangs off an order-inquiry row, and a retail sales-order line has none. Making
    the column nullable to hang one there would weaken a constraint four readers join on
    (`_allocations_for`, `links_for_rows`, `_allocated_by_po`, the sales-order detail's own
    "Linked to"), for a link no screen reads - retail has never carried one, for a purchase
    order either. The retail tick still counts: it is what put the quantity at that
    warehouse.

    Best-effort per row: a refusal names one row's own problem (its verb changed, the
    allocation moved), and failing the whole confirm - after the SPO, its lines and its
    allocations are already written - would leave the operator with a container they cannot
    re-create and no link either.
    """
    if not allocations or not any(ticked.values()):
        return []

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    service = ProjectOrderInquiryService(db)
    by_line: dict[str, list[dict]] = {}
    for allocation in allocations:
        by_line.setdefault(str(allocation["shipment_line_id"]), []).append(allocation)

    out: list[dict] = []
    for line_id, keys in ticked.items():
        pool = [dict(a) for a in by_line.get(line_id, [])]
        if not pool:
            continue
        for key in keys:
            if not key.startswith(f"{_COVERAGE_PROJECT}:"):
                continue
            row_id = key.split(":", 1)[1]
            row = (
                db.query(_inquiry_row_model())
                .filter(_inquiry_row_model().id == row_id)
                .first()
            )
            if row is None:
                continue
            need = float(row.qty or 0) - _linked_qty(db, row_id)
            if need <= 0:
                continue
            # The allocation at this row's OWN location first - that is what the tick put
            # there - then whatever else this line landed, because a row served from the
            # other half of the same container is still served.
            wanted_code = (row.stock_location or "").strip().upper() or None
            codes = _warehouse_ids_by_code(db) if wanted_code else {}
            preferred = codes.get(wanted_code) if wanted_code else None
            pool.sort(key=lambda a: 0 if str(a["warehouse_id"]) == str(preferred) else 1)
            for allocation in pool:
                if need <= 0:
                    break
                left = float(allocation.get("qty") or 0)
                if left <= 0:
                    continue
                take = min(need, left)
                try:
                    service.place_on_po_allocations(
                        row_id,
                        [{"spo_allocation_id": allocation["allocation_id"], "qty": take}],
                        actor_user_id=actor_user_id,
                    )
                except AppException as exc:  # noqa: PERF203 - one row's problem, not the batch's
                    logger.warning(
                        "SPO link refused for order inquiry row %s: %s", row_id, exc.detail
                    )
                    break
                allocation["qty"] = left - take
                need -= take
                out.append({
                    "key": key,
                    "document": row.item_code,
                    "spo_number": _spo_number_of(db, allocation["allocation_id"]),
                    "qty": take,
                })
    return out


def _inquiry_row_model():
    from app.models.project_so import OrderInquiryRow

    return OrderInquiryRow


def _linked_qty(db: Session, row_id: str) -> float:
    from app.models.project_so import OrderInquiryLink

    total = (
        db.query(func.coalesce(func.sum(OrderInquiryLink.qty), 0))
        .filter(OrderInquiryLink.row_id == str(row_id))
        .scalar()
    )
    return float(total or 0)


def _spo_number_of(db: Session, allocation_id: str) -> Optional[str]:
    return (
        db.query(SPOAllocation.spo_number)
        .filter(SPOAllocation.id == str(allocation_id))
        .scalar()
    )


def unwind(db: Session, shipment_id: str) -> dict:
    """Undo `create` for one shipment - the Delete action on an already-converted planner row
    (captain live case, 21 Aug: he created SPOs, then deleted their `spo_allocations` on the
    SPO Allocations screen, and had no way back to a clean "suggest" state because the SPO
    itself, and the link naming it, were both still there). Deletes the `purchase_order_lines`
    + `purchase_orders` headers this shipment's `create` minted, every `shipment_line_spo_link`
    row for the shipment (matched AND skipped - the whole create run, not half of it), and any
    `spo_allocations` still hanging off those PO lines. That last one is not automatic: the FK
    from `spo_allocations.po_line_id` is `ON DELETE SET NULL`, not `CASCADE` (a stock arrival
    can legitimately have no PO behind it), so deleting the PO line alone would leave a
    now-untraceable allocation still counting as incoming supply - the exact half-undone state
    this action exists to avoid.

    Since the doctrine correction (module docstring, fifth amendment), also REVERSES the
    `qty_received` `create` advanced on every SOURCE PO line these SPO lines pulled from -
    parsed back out of each deleted line's own `source_ref` JSON. Without this, deleting a CRM
    SPO would leave the source PO permanently short by whatever it lent, with no SPO left to
    explain where it went - a real loss, not merely an undo. Guarded the same defensive way
    `_heal_stale_links` is: a source line already gone by some other path is simply skipped,
    left to that function's own self-heal story rather than failing this one.

    Two hard guards, both refused with a 409 rather than a partial delete:
      * every header touched must carry `source_system == crm_spo` (`SOURCE_SYSTEM`) - an
        AutoCount import must never be deleted from this screen, however it ended up linked;
      * only headers actually LINKED TO THIS SHIPMENT are touched at all - the query never
        reaches a PO belonging to another shipment's conversion.

    After this, `suggest(db, shipment_id)` returns to its normal (non-`already_converted`)
    state - nothing is left behind to make the next `suggest` call answer any differently than
    a shipment that never ran "Create SPO" at all. Same permission as `create`
    (`scm.reorder.run`, enforced by the route) - unwinding a PO-book write is the same class of
    write as making one.
    """
    shipment = _shipment_or_404(db, shipment_id)
    links = _existing_links(db, shipment.id)
    if not links:
        raise AppException(404, "This shipment has no SPO to delete.")

    po_ids = {str(l.purchase_order_id) for l in links if l.purchase_order_id}
    if not po_ids:
        raise AppException(404, "This shipment has no SPO to delete.")

    pos = db.query(PurchaseOrder).filter(PurchaseOrder.id.in_(po_ids)).all()
    foreign = [po for po in pos if po.source_system != SOURCE_SYSTEM]
    if foreign:
        names = ", ".join(sorted({po.po_number or "?" for po in foreign}))
        raise AppException(
            409,
            f"{names} was not created by Create SPO and cannot be deleted from this screen.",
            detail="not_crm_spo",
        )

    po_numbers = sorted({po.po_number or "?" for po in pos})

    po_lines = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id.in_(po_ids))
        .all()
    )
    po_line_ids = [str(pl.id) for pl in po_lines]

    restored_source_lines = _reverse_advances(db, po_lines)

    deleted_allocations = 0
    if po_line_ids:
        deleted_allocations = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.po_line_id.in_(po_line_ids))
            .delete(synchronize_session=False)
        )

    for pl in po_lines:
        db.delete(pl)
    for po in pos:
        db.delete(po)
    for link in links:
        db.delete(link)
    db.flush()

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "deleted_po_numbers": po_numbers,
        "deleted_spo_count": len(pos),
        "deleted_allocation_count": deleted_allocations,
        "restored_po_line_count": restored_source_lines,
    }


def _parse_pulls(source_ref: Optional[str]) -> list[tuple[str, float]]:
    """`create`'s own encoding of `source_ref` on a `crm_spo` line - a JSON list of
    `{"po_line_id", "qty"}`. Anything else (absent, unparsable, an older/foreign line's own
    unrelated `source_ref` value) reads as "nothing to reverse" rather than raising - this is
    read defensively, on a delete path, not trusted input."""
    if not source_ref:
        return []
    try:
        data = json.loads(source_ref)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[tuple[str, float]] = []
    for item in data:
        try:
            out.append((str(item["po_line_id"]), float(item["qty"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _reverse_advances(db: Session, po_lines: list[PurchaseOrderLine]) -> int:
    """`unwind`'s own half of the fifth amendment: undo the `qty_received` bump `create` made
    on every SOURCE PO line these (about-to-be-deleted) `crm_spo` lines pulled from. Floored at
    zero rather than allowed to go negative - a source line touched again by something else
    since `create` ran must not be dragged below what IT now legitimately holds."""
    reversals: dict[str, float] = {}
    for pl in po_lines:
        for src_id, qty in _parse_pulls(pl.source_ref):
            reversals[src_id] = reversals.get(src_id, 0.0) + qty
    if not reversals:
        return 0
    sources = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id.in_(reversals.keys())).all()
    for src in sources:
        taken = reversals.get(str(src.id), 0.0)
        src.qty_received = max(float(src.qty_received or 0) - taken, 0.0)
    return len(sources)


# --------------------------------------------------------------------------- #
# the AutoCount handoff worksheet
# --------------------------------------------------------------------------- #

_COLUMNS = ["SUPPLIER", "MODEL", "DESCRIPTION", "QTY", "UNIT COST", "CURRENCY", "CRM SPO NO"]


def worksheet_payload(db: Session, shipment_id: str) -> dict:
    """What the office keys into AutoCount, read back from what `create` wrote. 404 when
    this shipment has never had "Create SPO" run - there is nothing to hand off yet."""
    shipment = _shipment_or_404(db, shipment_id)
    rows = (
        db.query(ShipmentLineSpoLink, InboundShipmentLine, PurchaseOrder)
        .join(InboundShipmentLine, InboundShipmentLine.id == ShipmentLineSpoLink.inbound_shipment_line_id)
        .outerjoin(PurchaseOrder, PurchaseOrder.id == ShipmentLineSpoLink.purchase_order_id)
        .filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id,
            ShipmentLineSpoLink.purchase_order_id.isnot(None),
        )
        .all()
    )
    if not rows:
        raise AppException(
            404,
            "No SPO has been created from this shipment yet.",
            detail="not_converted",
        )

    product_ids = [str(l.product_id) for _link, l, _po in rows]
    products = {
        str(pid): (code, name)
        for pid, code, name in db.query(*_product_cols()).filter(_product_id_in(product_ids)).all()
    }
    supplier_ids = {str(po.supplier_id) for _l, _sl, po in rows if po and po.supplier_id}
    suppliers = {
        str(s.id): s.supplier_name
        for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}

    lines = []
    for link, ship_line, po in rows:
        code, name = products.get(str(ship_line.product_id), (None, None))
        po_line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.id == link.purchase_order_line_id)
            .one_or_none()
        )
        lines.append({
            "supplier_name": suppliers.get(str(po.supplier_id)) if po else None,
            "product_code": code,
            "product_name": name,
            "qty": _f(po_line.qty_ordered) if po_line else None,
            "unit_cost": _f(po_line.unit_cost) if po_line else None,
            "currency": po_line.currency if po_line else None,
            "po_number": po.po_number if po else None,
        })
    lines.sort(key=lambda l: (l["supplier_name"] or "", l["product_code"] or ""))

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "container_no": shipment.shipping_container_number,
        "lines": lines,
    }


def to_xlsx(payload: dict) -> bytes:
    """The worksheet as a workbook - same pattern as `consolidated_packing_list.to_xlsx`."""
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active or wb.create_sheet()
    ws.title = "SPO WORKSHEET"
    bold = Font(bold=True)

    for label, value in (
        ("CONTAINER", payload.get("container_no") or payload.get("shipment_number")),
        ("SHIPMENT", payload.get("shipment_number")),
    ):
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = bold
    ws.append([])

    ws.append(list(_COLUMNS))
    for col in range(1, len(_COLUMNS) + 1):
        ws.cell(row=ws.max_row, column=col).font = bold

    for line in payload["lines"]:
        ws.append([
            line["supplier_name"],
            line["product_code"],
            line["product_name"],
            line["qty"],
            line["unit_cost"],
            line["currency"],
            line["po_number"],
        ])

    for i, width in enumerate([28, 18, 34, 10, 12, 10, 20], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_filename(payload: dict) -> str:
    import re

    stem = payload.get("container_no") or payload.get("shipment_number") or payload["shipment_id"]
    stem = re.sub(r"[^A-Za-z0-9._-]", "", str(stem)) or str(payload["shipment_id"])
    return f"{stem}-spo-worksheet.xlsx"
