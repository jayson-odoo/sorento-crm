"""The one visibility rule for an order inquiry row (OI-RESERVE-USED-ROW, owner 4 Nov 2026).

A row is LIVE, and so shown on Order Inquiries > Lines, counted by the Documents tab and
listed on the OI page's Lines tab, when it is not cancelled and not used
(`redirected_to_pool`). A used row's goods were released to the pool when its line changed;
a cancelled row was called off. Both stay readable as History on the OI page, and neither may
carry a new reserve request.

Owner ruling: "we show what in document tab, we hide what in document tab, also should tally
with the lines tab". So the worklist (`order_inquiry_worklist_service._base`), the Documents
counts (`order_inquiry_header_service._rows_agg`), the reserve request guard
(`order_inquiry_reserve_service.create_request`) and the stock debt snapshot drill all read
this module. The frontend twin is `isLiveInquiryRow` (`_shared/lib/orderInquiryLineFold.ts`).

OI-RESERVE-ANY-ROW (owner, 5 Nov 2026: "any row that is not Done are reservable ah, doesn't
matter the Delay or Advance or not"): a row is RESERVABLE when it is live and not Done, whatever
its verb. "Done" is the supply state `actioned` (the screen word `STATE_LABEL.actioned`,
`OrderInquiryVerbPill.tsx`); the states left on a live row are `INQUIRY_LINK_STATES`. Not the
handshake's Done (`ack_state = acknowledged`): OI-AUTO-CONFIRM acknowledges every non-buy row
automatically, so that reading would refuse every DELAY row. Readers: the reserve request guard,
the stock debt snapshot's `requestable`, the used-row repair's target. Frontend twin:
`isReservableInquiryRow`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_

from app.models.project_so import INQUIRY_CANCELLED, INQUIRY_LINK_STATES, OrderInquiryRow


def live_row_clause(row: Any = OrderInquiryRow):
    """SQL: the row is live. `row` is the mapped class or an alias of it."""
    return and_(row.state != INQUIRY_CANCELLED, row.redirected_to_pool.isnot(True))


def is_live_row(row: OrderInquiryRow) -> bool:
    return row.state != INQUIRY_CANCELLED and not bool(row.redirected_to_pool)


def reservable_row_clause(row: Any = OrderInquiryRow):
    """SQL: the row is live and not Done (`is_reservable_row`)."""
    return and_(row.state.in_(INQUIRY_LINK_STATES), row.redirected_to_pool.isnot(True))


def is_reservable_row(row: Any) -> bool:
    """Live and not Done, any verb: a reserve may be requested on it and reserved."""
    return row.state in INQUIRY_LINK_STATES and not bool(row.redirected_to_pool)
