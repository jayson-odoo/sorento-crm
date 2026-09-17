"""Reconstructed undo of a journal-less confirm revision (`PLAN-scm-oi-handover-r2-
undo.md`, S5, AC-R2-30..35).

Every revision confirmed before the journal existed (`undo_0001`, 17 Sep 04:37Z) has
`undo_journal IS NULL` - there is nothing for `project_supply_undo_service.undo_last_
confirm` to replay. This module does the SAME end result by a different route: reading
back what a Confirm's own writers (`ProjectOrderInquiryService.refresh_for_decision`,
the SO line allocator, the stock-transfer proposer) leave as EVIDENCE on the rows
themselves - `supply_decision_id`, `previous_qty` / `previous_delivery_date`, a note
naming the revision, `redirected_to_pool` - rather than a recorded script. It is a
best-effort restore, not a byte-for-byte replay: a saved draft, the note text a
supersede overwrote, an ack stamp, a link purchasing removed by hand, an open link a
release dropped, or a partly-linked shrink's pre-shrink qty are none of them
recoverable this way, and the gear entry / the email both say so.

`reconstruct_refusal` is the SAME `linked`/`actioned` shape `project_supply_undo_
service._grouped_refusals` checks for a journalled undo (AC-R2-32), read directly off
the rows D touched rather than off a journal's own insert-set exemption - there is no
journal here to exempt anything with. Called twice: once at PARK time
(`app.api.v1.system.pending_actions._assert_undo_not_refused`) and again here, first
thing, before any write.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.models.stock_transfer import StockTransfer, TRANSFER_CANCELLED, TRANSFER_PROPOSED
from app.services.audit_service import _model_to_audit_dict, log_audit
from app.services.error_handler import AppException
from app.services.project_order_inquiry_service import (
    ProjectOrderInquiryService,
    _handover_fmt_date,
    _qty_str,
)

#: How long after a decision's own confirm a row's own write still counts as "that
#: confirm's own doing" - the settle-in-place window (b) and, collapsed with the
#: cutoff below, the raise window (a) too.
_WINDOW_SECONDS = 60

_REFUSAL_MESSAGES = {
    "linked": "Purchasing has linked a PO line to this order since it was confirmed.",
    "actioned": "Purchasing has marked a row on this order actioned since it was confirmed.",
}


def reconstruct_refusal(db: Session, decision: SOSupplyDecision) -> Optional[str]:
    """AC-R2-32: refuse the SAME two ways a journalled undo does, read directly off
    D's own touched rows (`supply_decision_id = D.id`) rather than off a journal's own
    insert-set exemption - there is no journal here to carry one. A row still
    `actioned` after D's own confirm, or a link on one of D's rows written after D's
    own confirm, refuses; `None` when nothing purchasing did since blocks it.
    """
    row_ids = [
        row_id
        for (row_id,) in db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.supply_decision_id == decision.id)
        .all()
    ]
    if not row_ids:
        return None
    for row_id, actioned_at in (
        db.query(OrderInquiryRow.id, OrderInquiryRow.actioned_at)
        .filter(OrderInquiryRow.id.in_(row_ids), OrderInquiryRow.state == INQUIRY_ACTIONED)
        .all()
    ):
        if actioned_at and decision.confirmed_at and actioned_at > decision.confirmed_at:
            return "actioned"
    for linked_at, auto in (
        db.query(OrderInquiryLink.linked_at, OrderInquiryLink.auto)
        .filter(OrderInquiryLink.row_id.in_(row_ids))
        .all()
    ):
        if not auto and linked_at and decision.confirmed_at and linked_at > decision.confirmed_at:
            return "linked"
    return None


def reconstruct_undo(
    db: Session,
    order: ProjectSalesOrder,
    decision: SOSupplyDecision,
    *,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Best-effort undo of `decision` (D), a journal-less ACTIVE decision, back to
    whatever it superseded (P), or to nothing (AC-R2-31 a-h).

    Refuses (409, `linked`/`actioned`) before touching anything (AC-R2-32). Otherwise:
    rows D raised are deleted with their links; rows D settled in place are restored
    from their own `previous_qty`/`previous_delivery_date` and repointed to P; rows D
    cancelled or released are reinstated; D's own allocations/transfers are cleaned up
    or handed back to P; D is deleted with an audit DELETE row and P (if any)
    reactivated; no draft is ever written; one `order_inquiry_undone` email queues,
    headline `RECONSTRUCTED`.
    """
    refusal = reconstruct_refusal(db, decision)
    if refusal:
        raise AppException(status_code=409, message=_REFUSAL_MESSAGES[refusal], code=refusal)

    prior: Optional[SOSupplyDecision] = (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.id == decision.supersedes_id).first()
        if decision.supersedes_id
        else None
    )

    # AC-R2-31a's own wording ("created_at > P.confirmed_at") double-counts a row P
    # itself raised close to ITS OWN confirm (created_at just after P.confirmed_at,
    # long before D's) as "raised by D" - `_settle_row_in_place` never touches
    # `created_at`, so a row D only SETTLED still carries a creation stamp from back
    # when P first raised it. What the step actually means is "created after P
    # stopped being the active decision", which is D's OWN confirm - the same
    # instant `attach()` stamps as `P.superseded_at` - so both branches collapse to
    # one formula: D's own confirm, less a grace window for the same clock-skew the
    # "no P" fallback already names (a raise and its confirm land microseconds apart
    # inside one transaction).
    cutoff = decision.confirmed_at - timedelta(seconds=_WINDOW_SECONDS)

    oi_service = ProjectOrderInquiryService(db)
    removed_lines: List[Dict[str, Any]] = []
    restored_lines: List[Dict[str, Any]] = []

    touched_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.supply_decision_id == decision.id)
        .all()
    )
    raised_rows = [row for row in touched_rows if row.created_at and row.created_at > cutoff]
    remaining_rows = [row for row in touched_rows if row not in raised_rows]

    # (a) rows D raised: delete with their links (frees orphan claims).
    for row in raised_rows:
        removed_lines.append(
            {
                "item_code": row.item_code,
                "qty": _qty_str(row.qty),
                "delivery_date": _handover_fmt_date(row.delivery_date),
                "outcome": "removed",
            }
        )
        links = oi_service._links_of(row.id)
        if links:
            oi_service._remove_links(row, links)
        db.delete(row)
    db.flush()

    # (b) rows D settled or repointed: restore within the settle window, always
    # repoint to P (or NULL, no P).
    for row in remaining_rows:
        if (
            row.changed_at
            and decision.confirmed_at
            and abs((row.changed_at - decision.confirmed_at).total_seconds()) <= _WINDOW_SECONDS
        ):
            stamp = f"restored by reconstructed undo of revision {decision.revision_no}"
            row.note = f"{row.note}; {stamp}" if row.note else stamp
            if row.previous_qty is not None:
                row.qty = row.previous_qty
            row.delivery_date = row.previous_delivery_date
            row.previous_qty = None
            row.previous_delivery_date = None
            restored_lines.append(
                {
                    "item_code": row.item_code,
                    "qty": _qty_str(row.qty),
                    "delivery_date": _handover_fmt_date(row.delivery_date),
                    "outcome": "restored",
                }
            )
        row.supply_decision_id = prior.id if prior else None
    db.flush()

    inquiry_id = (
        db.query(OrderInquiry.id)
        .filter(
            OrderInquiry.project_sales_order_id == order.id,
            OrderInquiry.amendment_id.is_(None),
        )
        .scalar()
    )
    if inquiry_id:
        # (c) rows D cancelled (a plain supersede this D's own confirm wrote):
        # reinstated to raised.
        superseded_note = f"Superseded by revision {decision.revision_no}"
        for row in (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry_id,
                OrderInquiryRow.state == INQUIRY_CANCELLED,
                OrderInquiryRow.note == superseded_note,
            )
            .all()
        ):
            row.state = INQUIRY_RAISED
            stamp = "reinstated by reconstructed undo"
            row.note = f"{row.note}; {stamp}" if row.note else stamp
            restored_lines.append(
                {
                    "item_code": row.item_code,
                    "qty": _qty_str(row.qty),
                    "delivery_date": _handover_fmt_date(row.delivery_date),
                    "outcome": "reinstated",
                }
            )

        # (d) rows D released (redirected to the pool): flagged back.
        released_marker = f"released at revision {decision.revision_no}"
        for row in (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry_id,
                OrderInquiryRow.redirected_to_pool.is_(True),
                OrderInquiryRow.note.contains(released_marker),
            )
            .all()
        ):
            row.redirected_to_pool = False
            restored_lines.append(
                {
                    "item_code": row.item_code,
                    "qty": _qty_str(row.qty),
                    "delivery_date": _handover_fmt_date(row.delivery_date),
                    "outcome": "re-covered",
                }
            )
    db.flush()

    # (e) D's own allocations and transfers. Loaded and disposed of one ORM object
    # at a time - like every other write in this function - rather than a bulk
    # `Query.delete()`/`.update()`: a bulk operation does not give the SAME object
    # already sitting in THIS session's identity map (a caller's own fixture
    # reference, say) the ordinary `db.delete()` lifecycle, and a later attribute
    # read on it after commit raises `DetachedInstanceError`/`ObjectDeletedError`
    # instead of the clean "gone" a plain `db.delete()` leaves behind.
    for allocation in (
        db.query(SOLineAllocation).filter(SOLineAllocation.decision_id == decision.id).all()
    ):
        db.delete(allocation)
    for transfer in (
        db.query(StockTransfer)
        .filter(
            StockTransfer.supply_decision_id == decision.id,
            StockTransfer.state == TRANSFER_PROPOSED,
        )
        .all()
    ):
        db.delete(transfer)
    # A transfer D's own confirm CANCELLED (superseding an earlier revision's
    # proposal) has its `supply_decision_id` cleared to `None` at cancel time - the
    # same pattern a cancelled `order_inquiry_rows` row follows (c) - so this one is
    # found by `cancelled_reason` text, scoped to THIS order, never by `supply_
    # decision_id = D.id`.
    transfer_cancelled_reason = f"Superseded by revision {decision.revision_no}"
    for transfer in (
        db.query(StockTransfer)
        .filter(
            StockTransfer.project_sales_order_id == order.id,
            StockTransfer.state == TRANSFER_CANCELLED,
            StockTransfer.cancelled_reason == transfer_cancelled_reason,
        )
        .all()
    ):
        transfer.state = TRANSFER_PROPOSED
        transfer.supply_decision_id = prior.id if prior else None
        transfer.cancelled_reason = None
    db.flush()

    # (f) D deleted with the same audit DELETE the journal undo writes; P reactivated.
    audit_old_values = _model_to_audit_dict(decision)
    audit_old_values.pop("undo_journal", None)
    log_audit(
        db,
        "project_so_supply_decisions",
        str(decision.id),
        "DELETE",
        old_values=audit_old_values,
        user_id=actor_user_id,
        company_id=decision.company_id,
    )
    decision_id = decision.id
    revision_no = decision.revision_no
    # D's own DELETE flushes on its own, before P is reactivated: `uq_so_supply_
    # decisions_active` allows only one ACTIVE row per order, and D (still active)
    # and P (about to become active) would otherwise coexist within the same flush.
    db.delete(decision)
    db.flush()
    if prior:
        prior.state = DECISION_ACTIVE
        prior.superseded_at = None
        prior.superseded_reason = None
        db.flush()

    # (g) nothing here ever writes an `SOSupplyDecisionDraft` row.

    # (h) one order_inquiry_undone email, headline RECONSTRUCTED.
    oi_service._record_undo(
        pso_id=str(order.id),
        decision_id=str(decision_id),
        revision_no=revision_no,
        lines=removed_lines + restored_lines,
        actor_user_id=actor_user_id,
        headline="RECONSTRUCTED",
    )

    return {
        "revision_no": revision_no,
        "restored_to": prior.revision_no if prior else None,
    }
