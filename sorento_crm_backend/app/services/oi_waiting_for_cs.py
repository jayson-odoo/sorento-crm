"""The one rule for "waiting for CS" (OI-WHOLE-SO-CANCEL v2, AC-V2-2, owner rule 12 Nov 2026).

An order inquiry row is waiting for CS exactly while its SO line has a PENDING planning-change
row in an UNAPPLIED batch. Derived, no column: it clears by itself when CS's Confirm applies
the batch, or when a later batch supersedes the pending row. Purchasing cannot acknowledge a
waiting row, the system's own auto-confirm skips it, and `ack=to_confirm` leaves it out.

SPARE-PART-OR-B C (C4.2 / C4.3): an order request row waits the same way while a revision is
open on its header (draft, pending approval or rejected) and that revision moved the row: its
qty, product or delivery date differs, or it is to be removed (`revised_qty` 0). The revision's
final approval is the request's CS Confirm; it settles the row and clears the revision fields.
"""
from __future__ import annotations

from typing import Any, Iterable, Set

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import OrderInquiryRow
from app.services.planning_change_service import PLANNING_CHANGE_STATE_PENDING

WAITING_FOR_CS_MESSAGE = "Waiting for CS to confirm the sales order change"


def pending_change_clause(so_line_id: Any):
    """SQL: a pending planning-change row names the mirror line `so_line_id` (a column, so
    this correlates into the enclosing query)."""
    return (
        PlanningChangeRow.project_line_id == so_line_id,
        PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_PENDING,
        PlanningChangeBatch.id == PlanningChangeRow.batch_id,
        PlanningChangeBatch.applied_at.is_(None),
    )


def revision_moved_clause(row: Any = OrderInquiryRow):
    """SQL: an open revision of the row's order request moved the row (C4.2). The revision
    fields are set only while a revision is open (every path that closes one clears them,
    `spare_part_request_service._clear_revision`), so they alone say so."""
    return or_(
        and_(row.revised_qty.isnot(None), row.revised_qty != row.qty),
        and_(
            row.revised_product_id.isnot(None),
            row.revised_product_id.is_distinct_from(row.product_id),
        ),
        and_(
            row.revised_delivery_date.isnot(None),
            row.revised_delivery_date.is_distinct_from(row.delivery_date),
        ),
    )


def waiting_for_cs_clause(row: Any = OrderInquiryRow):
    """SQL: the row is waiting for CS, on an SO change or an order request revision. `row`
    is the mapped class or an alias."""
    return or_(exists().where(*pending_change_clause(row.so_line_id)), revision_moved_clause(row))


def waiting_row_ids(db: Session, row_ids: Iterable[str]) -> Set[str]:
    """Which of `row_ids` are waiting for CS, one query."""
    ids = [str(i) for i in row_ids if i]
    if not ids:
        return set()
    # The lines an apply is deciding right now do not wait on that very apply (screens still read
    # the plain EXISTS above, which is true until the apply commits).
    from app.services.planning_change_service import APPLYING_LINE_IDS_KEY

    applying = db.info.get(APPLYING_LINE_IDS_KEY) or set()
    query = db.query(OrderInquiryRow.id).filter(OrderInquiryRow.id.in_(ids), waiting_for_cs_clause())
    if applying:
        query = query.filter(
            or_(
                OrderInquiryRow.so_line_id.is_(None),
                OrderInquiryRow.so_line_id.notin_(list(applying)),
            )
        )
    found = query.all()
    return {str(r[0]) for r in found}
