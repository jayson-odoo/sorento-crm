"""What counts as incoming supply on an SPO allocation. ONE rule, four readers.

`scm.on_order_v`, the fulfilment ladder's rung 1 (`project_supply_service._spo_rows`, which
also feeds the board's cell popover), the order inquiry's inbound pool and the coverage
screen's "already on order" figure all have to answer the same question, or the planner is
shown one number and the engine decides on another. The clauses live here so there is one
copy in Python; the view repeats them in SQL and names this module.

Two rules, and each is a fact about the data rather than a preference.

**A shipping order nobody has booked a container for, whose promised date has passed, is
STALE and is not supply.** Measured on the captain's book on 26 August 2026: all 715 open SPO
lines (39,110 units) carry an `expected_date` in the past, the oldest 2024-06-28, and nothing
refreshes them - `outstanding_reader` skips every `SPO-` row of the purchase book, so the
only feed that could restate them does not carry them. Counted as supply they suppress real
purchases for ever, silently, on the strength of a date two years old.

**A shipment-backed row is never stale.** Once a container exists the arrival is tracked -
`estimated_arrival_date`, `eta_delay_date`, `actual_arrival_date` are maintained by the
packing-list channel - so a late container is late, not imaginary, and dropping it would hide
stock that is genuinely on the water.

A row with NO date at all is not stale either: there is no evidence its date has passed. It
can never be TIMELY (rung 1 needs an arrival on or before the required date), so it can
offer cover to nobody, but it is still a real order and it stays in the on-order figure.

The boundary is inclusive: `expected_date == as_of` means it arrives today, which is supply.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import or_

from app.models.procurement import InboundShipment, SPOAllocation

#: Receipt statuses that mean the goods are in. `fully_received` is the value the column's
#: own CHECK constraint allows; `received` is kept beside it because migration 337's view
#: was written against that spelling, which no row has ever carried - a `<> 'received'`
#: test that can never be false is a filter that looks like a guard and is not one.
RECEIVED_RECEIPT_STATUSES = ("fully_received", "received")


def open_incoming_clauses(as_of: date) -> tuple:
    """The four tests a row must pass to be supply, for a query that has outer-joined
    `InboundShipment` onto `SPOAllocation.inbound_shipment_id`."""
    return (
        # A closed line has left the book, the same way a closed purchase line has.
        or_(SPOAllocation.line_status.is_(None), SPOAllocation.line_status == "open"),
        or_(
            SPOAllocation.receipt_status.is_(None),
            SPOAllocation.receipt_status.notin_(RECEIVED_RECEIPT_STATUSES),
        ),
        # Landed is not incoming.
        or_(InboundShipment.id.is_(None), InboundShipment.actual_arrival_date.is_(None)),
        not_stale_clause(as_of),
    )


def not_stale_clause(as_of: date):
    """The staleness rule on its own, for a reader that scopes the rest differently."""
    return or_(
        SPOAllocation.inbound_shipment_id.isnot(None),
        SPOAllocation.expected_date.is_(None),
        SPOAllocation.expected_date >= as_of,
    )


def is_stale(*, has_shipment: bool, expected_date: date | None, as_of: date) -> bool:
    """The same rule for a row already in hand, so a caller that has read the row does not
    re-derive it from its own reading of the sentence above."""
    if has_shipment or expected_date is None:
        return False
    return expected_date < as_of
