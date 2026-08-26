"""What counts as incoming supply on an SPO allocation. ONE rule, four readers.

`scm.on_order_v`, the fulfilment ladder's rung 1 (`project_supply_service._spo_rows`, which
also feeds the board's cell popover), the order inquiry's inbound pool and the coverage
screen's "already on order" figure all have to answer the same question, or the planner is
shown one number and the engine decides on another. The clauses live here so there is one
copy in Python; the view repeats them in SQL and names this module.

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
so a buyer reading the trail or the popover can see which promise is being leaned on and go
and chase it. That is the honest treatment: visible, not silently dropped and not silently
counted as if it were fresh.

Rung 1 is unchanged by this: it needs `expected_date <= required_date`, which a past date
always satisfies, and a row with NO date can never be timely, so it covers nobody however
open it is.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import or_

from app.models.procurement import InboundShipment, SPOAllocation

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
