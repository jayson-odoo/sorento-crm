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
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_

from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow


def live_row_clause(row: Any = OrderInquiryRow):
    """SQL: the row is live. `row` is the mapped class or an alias of it."""
    return and_(row.state != INQUIRY_CANCELLED, row.redirected_to_pool.isnot(True))


def is_live_row(row: OrderInquiryRow) -> bool:
    return row.state != INQUIRY_CANCELLED and not bool(row.redirected_to_pool)
