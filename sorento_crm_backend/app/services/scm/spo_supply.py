"""What counts as incoming supply on an SPO allocation. ONE rule, four readers.

`scm.on_order_v`, the fulfilment ladder's question 1 (`project_supply_service._spo_rows` and
`_group_water`, which also feed the board's cell popover), the order inquiry's inbound pool
and the coverage screen's "already on order" figure all have to answer the same question, or
the planner is shown one number and the engine decides on another. The clauses live here so
there is one copy in Python; the view repeats them in SQL and names this module.

**TRUST THE BOOK** (captain's ruling, 26 August 2026). An SPO line is incoming supply while
it is OPEN and something is still to come on it - allocated minus received above zero, a
receipt status that is not `fully_received`, a line status that is not closed - and it stays
supply until the re-uploaded PO & SPO book says it arrived. A promised date that has passed
does NOT remove it. The book is the record of what was bought and what is still owed; a date
is a promise about when, and a supplier being late is not evidence that the goods stopped
existing. Dropping 715 open lines because their dates are old would tell the planner to buy
39,110 units a second time.

What a passed date DOES change is the wording, not the arithmetic. The row is stated as
OVERDUE wherever it is named - "SPO-2026/08-0061 arrives on 1 Aug 2026 (overdue 25 days)" -
so a buyer reading the popover or the order-inquiry row can see which promise is being
leaned on and go and chase it. That is the honest treatment: visible, not silently dropped
and not silently counted as if it were fresh.

LADDER V5 (section 1e, and the water ruling of 27 August 2026) reads these rows twice, and
the two readings are deliberately different:

* the ownership GROUP's net counts every open row with NO arrival-date term at all, because
  it states the group's position rather than any one line's promise;
* what a LINE may draw off that water is only the share arriving on or before its own
  required date. A past date always satisfies that test, so an overdue promise still covers
  its line and is named with its date; a row dated after the line, or carrying no date at
  all, is named in question 1's own sentence and drawn by nobody.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, or_

from app.models.procurement import InboundShipment, SPOAllocation, Supplier

#: Receipt statuses that mean the goods are in. `fully_received` is the value the column's
#: own CHECK constraint allows; `received` is kept beside it because migration 337's view
#: was written against that spelling, which no row has ever carried - a `<> 'received'`
#: test that can never be false is a filter that looks like a guard and is not one.
RECEIVED_RECEIPT_STATUSES = ("fully_received", "received")


def open_incoming_clauses() -> tuple:
    """The three tests a row must pass to be supply, for a query that has outer-joined
    `InboundShipment` onto `SPOAllocation.inbound_shipment_id`.

    The quantity test (`allocated > received`) is deliberately NOT here: two of the four
    readers apply it in Python on the row they have already read, and one of those nets it
    against a running balance. It is stated once per reader, beside the arithmetic it
    belongs to.
    """
    return (
        # A closed line has left the book, the same way a closed purchase line has.
        or_(SPOAllocation.line_status.is_(None), SPOAllocation.line_status == "open"),
        or_(
            SPOAllocation.receipt_status.is_(None),
            SPOAllocation.receipt_status.notin_(RECEIVED_RECEIPT_STATUSES),
        ),
        # Landed is not incoming. Only a shipment can say a row has landed; an SPO with no
        # container booked has nothing that could have arrived.
        or_(InboundShipment.id.is_(None), InboundShipment.actual_arrival_date.is_(None)),
    )


def overdue_days(arrival_date: Optional[date], as_of: Optional[date] = None) -> int:
    """How many days late a promised arrival is. 0 when it is today, ahead, or unstated.

    The one copy of this arithmetic. It decides only how a row is WORDED - the row is supply
    either way - so a reader that does not name its rows on screen has no need to call it.
    """
    if arrival_date is None:
        return 0
    reference = as_of or date.today()
    return max((reference - arrival_date).days, 0)


def spo_history_for_product(db, run_id: str, product_id: str) -> dict:
    """The SPO book behind a plan row's SPO cell: open first, then what has landed.

    Scoped to the row's SITE POOL and nothing else (R15). A run writes recommendations for
    the locations that carry demand, which on live data is usually a project BIN rather
    than the pool itself, so the pool is resolved the same way every other reader resolves
    it - ``COALESCE(warehouses.pool_warehouse_id, warehouses.id)`` off the run's own rows
    for this product. A shipment bound for a project bin, or for another site entirely, is
    absent: the cell it explains deliberately excludes both.

    `open` uses the one rule in this module (`open_incoming_clauses` plus "something is
    still to come"); everything else the pool has ever been promised is history. Both are
    newest-promise-first, so a buyer reads the next arrival at the top.
    """
    from sqlalchemy import text as _text

    # BOTH ways a run states where a row's demand sits. A location-grain row names its
    # warehouse on the column; a PRODUCT-grain row names NONE - it is one buy for the whole
    # product, and the locations it was netted over live in the frozen
    # `inputs.plan_basis.locations` (`_emit_product`). Reading only the column returned an
    # empty book for every row on the live plan, which is the shape the rollout default
    # produces.
    pool_ids = [
        r[0] for r in db.execute(_text("""
            SELECT DISTINCT COALESCE(w.pool_warehouse_id, w.id)::text
              FROM scm.reorder_recommendation rr
              JOIN warehouses w ON w.id = rr.warehouse_id
             WHERE rr.run_id = CAST(:run AS uuid)
               AND rr.product_id = CAST(:pid AS uuid)
            UNION
            SELECT DISTINCT COALESCE(lw.pool_warehouse_id, lw.id)::text
              FROM scm.reorder_recommendation rr
              CROSS JOIN LATERAL jsonb_array_elements(
                  COALESCE(rr.inputs -> 'plan_basis' -> 'locations', '[]'::jsonb)) loc
              JOIN warehouses lw ON lw.id = CAST(loc ->> 'warehouse_id' AS uuid)
             WHERE rr.run_id = CAST(:run AS uuid)
               AND rr.product_id = CAST(:pid AS uuid)
        """), {"run": run_id, "pid": product_id}).all()
    ]
    if not pool_ids:
        return {"open": [], "history": []}

    # ORM, not raw SQL, for two reasons. The company isolation filter runs on ORM
    # execution only, and this reads a company-owned table (`SPOAllocation` is
    # `CompanyScopedMixin`) - raw SQL here would have listed another company's shipping
    # orders. And the open/closed test is `open_incoming_clauses()` itself, evaluated in
    # SQL and returned per row, rather than a second Python copy of the same three
    # conditions that could drift from the module they are meant to share.
    rows = (
        db.query(
            SPOAllocation.spo_number,
            Supplier.supplier_name,
            SPOAllocation.allocated_quantity,
            SPOAllocation.quantity_received,
            SPOAllocation.expected_date,
            InboundShipment.actual_arrival_date,
            and_(*open_incoming_clauses()).label("is_open"),
        )
        .outerjoin(Supplier, Supplier.id == SPOAllocation.supplier_id)
        .outerjoin(InboundShipment,
                   InboundShipment.id == SPOAllocation.inbound_shipment_id)
        .filter(
            SPOAllocation.product_id == product_id,
            SPOAllocation.warehouse_id.in_(pool_ids),
        )
        .order_by(SPOAllocation.expected_date.desc().nullslast(),
                  SPOAllocation.spo_number)
        .all()
    )

    open_rows: list[dict] = []
    history: list[dict] = []
    for r in rows:
        allocated = float(r.allocated_quantity or 0)
        received = float(r.quantity_received or 0)
        arrived = r.actual_arrival_date
        # The quantity test is the reader's own half of the rule (see
        # `open_incoming_clauses`' docstring): something still has to be to come.
        still_open = bool(r.is_open) and allocated > received
        entry = {
            "spo_number": r.spo_number,
            "supplier_name": r.supplier_name,
            "qty": allocated,
            "received_qty": received,
            "eta": r.expected_date.isoformat() if r.expected_date else None,
            "arrived_at": arrived.isoformat() if arrived else None,
            "status": _shipment_status(still_open, allocated, received, arrived),
        }
        (open_rows if still_open else history).append(entry)
    return {"open": open_rows, "history": history}


def _shipment_status(still_open: bool, allocated: float, received: float, arrived) -> str:
    """What the row IS, in the reader's words - never the raw column value.

    Two different columns say a shipment has landed (`receipt_status` and the shipment's
    own arrival date), and the book carries both spellings of "received"
    (`RECEIVED_RECEIPT_STATUSES`), so printing either one raw would show the same state
    under three different names in one table.
    """
    if still_open:
        return "Partly received" if received > 0 else "On the water"
    if arrived is not None and received <= 0:
        return "Arrived"
    if 0 < received < allocated:
        return "Partly received"
    return "Received"
