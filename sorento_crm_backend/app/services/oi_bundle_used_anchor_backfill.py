"""Backfill: move a companion row's stale `bundled_with_row_id` anchor off a USED host row.

SO314592 (prod, 21 Sep 2026): before `_is_host_row` (`project_order_inquiry_service.py`)
excluded `redirected_to_pool`, `derive_bundles` could pick an already-USED host row as a
companion's display anchor - 2 rows on 1 inquiry (SO314592 SRTWC8605-SC-RL) measured live.
`_is_host_row` stops that happening going forward; this module is the one-time catch-up
for whatever an earlier pass left anchored on a used row.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, aliased

from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
from app.services.project_order_inquiry_service import ProjectOrderInquiryService


def rebundle_rows_anchored_on_used_hosts(db: Session) -> int:
    """Re-run `derive_bundles` for every inquiry holding a row whose `bundled_with_row_id`
    still points at a USED (`redirected_to_pool`) host row, which moves the anchor onto
    the live host `_is_host_row` picks today. Idempotent: once `derive_bundles` has moved
    a row's anchor, that row no longer matches the predicate below, so a second call finds
    nothing and returns 0.

    Returns the number of rows found still anchored on a used host (before re-derivation).
    """
    host = aliased(OrderInquiryRow)
    stale = (
        db.query(OrderInquiryRow.id, OrderInquiryRow.order_inquiry_id)
        .join(host, host.id == OrderInquiryRow.bundled_with_row_id)
        .filter(
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.bundled_with_row_id.isnot(None),
            host.redirected_to_pool.is_(True),
        )
        .all()
    )
    if not stale:
        return 0

    inquiry_ids = {row.order_inquiry_id for row in stale}
    service = ProjectOrderInquiryService(db)
    for inquiry_id in inquiry_ids:
        service.derive_bundles(inquiry_id)
    return len(stale)
