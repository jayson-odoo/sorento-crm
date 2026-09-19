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
    "no_confirmed_at": "This confirm cannot be reconstructed.",
}


def _inquiry_ids_for_pso_ids(db: Session, pso_ids) -> List[str]:
    if not pso_ids:
        return []
    return [
        row_id
        for (row_id,) in db.query(OrderInquiry.id)
        .filter(
            OrderInquiry.project_sales_order_id.in_(pso_ids),
            OrderInquiry.amendment_id.is_(None),
        )
        .all()
    ]


def _sibling_decisions(db: Session, decision: SOSupplyDecision) -> List[SOSupplyDecision]:
    """Every OTHER `SOSupplyDecision` this same journal-less confirm transaction
    touched (S3, review round 1): a donor's own re-issue is a SEPARATE decision,
    on the DONOR's own order, sharing this one's exact `confirmed_at` - the
    literal `datetime.utcnow()` the write path stamps every decision one
    transaction commits with - which is the only signal a journal-less confirm
    leaves behind naming it (mirrors `project_supply_undo_service._pso_ids_by_
    decision`'s own journal-less fallback, kept local here because callers in
    this file need each sibling's own `revision_no` too, not only its order:
    a donor's own cancelled/released row is stamped "Superseded by revision N" /
    "released at revision N" with the DONOR's OWN revision number, never D's).
    """
    if not decision.company_id or decision.confirmed_at is None:
        return []
    return (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.company_id == decision.company_id,
            SOSupplyDecision.confirmed_at == decision.confirmed_at,
            SOSupplyDecision.id != decision.id,
        )
        .all()
    )


def _return_batch_to_pending(
    db: Session,
    order: ProjectSalesOrder,
    revision_no: int,
    confirmed_at: Optional[Any],
) -> None:
    """AC-R2-19a: the planning-change batch that minted this revision goes back to
    `pending`, and its `applied_at` clears once no applied row of it remains.

    The journal undo gets this for free - it replays every table the confirm touched,
    `planning_change_rows` included. A reconstructed undo has no journal, so the link has
    to be found rather than replayed, and there are two ways to find it:

    * THE STAMP, for anything applied since AC-R2-19a shipped:
      `result_json["supply_decision_revision_no"]`, written by
      `planning_change_service._apply_one_order` on every row it applies. Exact - the row
      already carries `project_sales_order_id`, and `(order, revision_no)` is UNIQUE on
      `so_supply_decisions`.
    * THE WINDOW, for a batch applied BEFORE that stamp existed, which is a closed set
      that shrinks to nothing: this order's applied rows whose batch was applied within
      `_WINDOW_SECONDS` of the confirm. Used ONLY when no row of this order carries a
      stamp at all, so a stamped batch never falls back to guessing, and the false
      positive the window alone would allow (a plain board Confirm seconds after an
      unrelated apply) cannot happen once the stamp is there. The trigger that justifies
      keeping it: prod's SO314594 was applied on 16 Sep by batch
      `bbde6b2d-2efb-4be7-a0ca-b6a399c510bc`, and the owner's recovery is an undo of
      exactly that revision.

    A revision from a plain board Confirm matches neither and touches no batch, which is
    the whole of "A revision from a plain confirm touches no batch" in the AC.
    """
    from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
    from app.services.planning_change_service import (
        PLANNING_CHANGE_STATE_APPLIED,
        PLANNING_CHANGE_STATE_PENDING,
    )

    applied_rows = (
        db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.project_sales_order_id == str(order.id),
            PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_APPLIED,
        )
        .all()
    )
    if not applied_rows:
        return
    returning = [
        row
        for row in applied_rows
        if (row.result_json or {}).get("supply_decision_revision_no") == revision_no
    ]
    if not returning and confirmed_at is not None:
        edge = timedelta(seconds=_WINDOW_SECONDS)
        stamped_ids = {
            row.batch_id
            for row in applied_rows
            if (row.result_json or {}).get("supply_decision_revision_no") is not None
        }
        applied_at_by_batch = dict(
            db.query(PlanningChangeBatch.id, PlanningChangeBatch.applied_at)
            .filter(
                PlanningChangeBatch.id.in_({row.batch_id for row in applied_rows}),
                PlanningChangeBatch.applied_at.isnot(None),
            )
            .all()
        )
        returning = [
            row
            for row in applied_rows
            if row.batch_id not in stamped_ids
            and applied_at_by_batch.get(row.batch_id) is not None
            and abs((applied_at_by_batch[row.batch_id] - confirmed_at).total_seconds())
            <= edge.total_seconds()
        ]
    if not returning:
        return

    for row in returning:
        row.applied_state = PLANNING_CHANGE_STATE_PENDING
        row.applied_reason = None
        # The row is pending again, so it has no result. Same end state the journal undo
        # reaches by restoring this column's pre-apply value, which was NULL.
        row.result_json = None
    db.flush()

    for batch_id in {row.batch_id for row in returning}:
        still_applied = (
            db.query(PlanningChangeRow.id)
            .filter(
                PlanningChangeRow.batch_id == batch_id,
                PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_APPLIED,
            )
            .first()
        )
        if still_applied is not None:
            # Another order of the same batch is still applied - its own undo clears the
            # batch when it runs. A batch is applied as a whole and un-applied one order
            # at a time.
            continue
        batch = (
            db.query(PlanningChangeBatch)
            .filter(PlanningChangeBatch.id == batch_id)
            .one_or_none()
        )
        if batch is not None:
            batch.applied_at = None
            batch.applied_by = None
    db.flush()


def _touched_pso_ids_and_revisions(db: Session, decision: SOSupplyDecision):
    """`(pso_ids, revision_nos, decision_ids)` for `decision` and every sibling
    `_sibling_decisions` finds - what every caller in this file needs: WHICH
    orders' inquiries to search, WHICH revision numbers to match note text
    against, and WHICH decisions' own `supply_decision_id` rows count as
    "touched" at all (S3: a donor's own re-issue raises/settles rows under ITS
    OWN decision id, never D's).
    """
    siblings = _sibling_decisions(db, decision)
    touched = [decision, *siblings]
    pso_ids = {d.project_sales_order_id for d in touched}
    revision_nos = {d.revision_no for d in touched}
    decision_ids = {d.id for d in touched}
    return pso_ids, revision_nos, decision_ids


def _touched_row_ids(db: Session, decision_ids, pso_ids, revision_nos) -> set:
    """Every row a reconstruct of D will touch, the SAME rule `reconstruct_undo`'s
    own steps (a)/(b)/(c)/(d) use (security review S3, review round 1): every
    TOUCHED decision's own rows (`supply_decision_id IN decision_ids` - a
    donor's re-issue raises/settles rows under ITS OWN decision id, never D's,
    so `== D.id` alone does not find them) PLUS every TOUCHED order's own rows
    cancelled "Superseded by revision N" PLUS its own rows released "released
    at revision N", for ANY of the touched decisions' own revision numbers - the
    two note-matched sets a donor's own supersede/release leaves behind with no
    `supply_decision_id` at all. `reconstruct_refusal` reads this same set so a
    purchasing action on a donor's own row refuses exactly as one on the
    borrower's own row does; `reconstruct_undo` reads it again to know what to
    restore.
    """
    row_ids = {
        row_id
        for (row_id,) in db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.supply_decision_id.in_(decision_ids))
        .all()
    }
    inquiry_ids = _inquiry_ids_for_pso_ids(db, pso_ids)
    if inquiry_ids and revision_nos:
        superseded_notes = [f"Superseded by revision {n}" for n in revision_nos]
        released_markers = [f"released at revision {n}" for n in revision_nos]
        row_ids |= {
            row_id
            for (row_id,) in db.query(OrderInquiryRow.id)
            .filter(
                OrderInquiryRow.order_inquiry_id.in_(inquiry_ids),
                OrderInquiryRow.state == INQUIRY_CANCELLED,
                OrderInquiryRow.note.in_(superseded_notes),
            )
            .all()
        }
        for row_id, note in (
            db.query(OrderInquiryRow.id, OrderInquiryRow.note)
            .filter(
                OrderInquiryRow.order_inquiry_id.in_(inquiry_ids),
                OrderInquiryRow.redirected_to_pool.is_(True),
            )
            .all()
        ):
            if note and any(marker in note for marker in released_markers):
                row_ids.add(row_id)
    return row_ids


def reconstruct_refusal(db: Session, decision: SOSupplyDecision) -> Optional[str]:
    """AC-R2-32: refuse the SAME two ways a journalled undo does, read directly off
    every row a reconstruct of D would touch (`_touched_row_ids`, S3) rather than
    off a journal's own insert-set exemption - there is no journal here to carry
    one. A row still `actioned` after D's own confirm, or a link landing more than
    the settle window after D's own confirm, refuses; `None` when nothing
    purchasing did since blocks it.

    B1 (review round 1): `auto` is not read at all any more. A cascade-placed link
    that lands INSIDE the window is the confirm's own doing whichever flag it
    carries; one that lands well OUTSIDE it (an AutoCount pairing that ran later)
    is purchasing acting on the order since, exactly like a manual link - the
    WINDOW is what tells the two apart, not the flag.
    """
    if decision.confirmed_at is None:
        return "no_confirmed_at"

    pso_ids, revision_nos, decision_ids = _touched_pso_ids_and_revisions(db, decision)
    row_ids = list(_touched_row_ids(db, decision_ids, pso_ids, revision_nos))
    if not row_ids:
        return None
    for row_id, actioned_at in (
        db.query(OrderInquiryRow.id, OrderInquiryRow.actioned_at)
        .filter(OrderInquiryRow.id.in_(row_ids), OrderInquiryRow.state == INQUIRY_ACTIONED)
        .all()
    ):
        if actioned_at and actioned_at > decision.confirmed_at:
            return "actioned"
    window_edge = decision.confirmed_at + timedelta(seconds=_WINDOW_SECONDS)
    for linked_at, _auto in (
        db.query(OrderInquiryLink.linked_at, OrderInquiryLink.auto)
        .filter(OrderInquiryLink.row_id.in_(row_ids))
        .all()
    ):
        if linked_at and linked_at >= window_edge:
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

    # S3 (review round 1): a cross-project borrow's donor re-issue is a SEPARATE
    # decision on the DONOR's own order, confirmed inside the SAME transaction as
    # D - `_sibling_decisions` is the same multi-order reach the journalled path
    # already gets from its journal, degraded (for a journal-less decision) to a
    # same-`confirmed_at` sibling match instead. `prior_by_pso_id` matters because
    # a donor's own prior decision is NEVER `prior` (D's own `supersedes_id`) - a
    # donor row repointed to the wrong order's prior would corrupt that order's
    # own decision chain, not just fail to restore this one's.
    siblings = _sibling_decisions(db, decision)
    touched_decisions = [decision, *siblings]
    touched_decision_ids = {d.id for d in touched_decisions}
    pso_ids = {d.project_sales_order_id for d in touched_decisions}
    revision_nos = {d.revision_no for d in touched_decisions}
    inquiry_ids = _inquiry_ids_for_pso_ids(db, pso_ids)
    prior_by_pso_id: Dict[str, Optional[str]] = {decision.project_sales_order_id: decision.supersedes_id}
    prior_by_decision_id: Dict[str, Optional[str]] = {decision.id: decision.supersedes_id}
    for sibling in siblings:
        prior_by_pso_id[sibling.project_sales_order_id] = sibling.supersedes_id
        prior_by_decision_id[sibling.id] = sibling.supersedes_id

    # AC-R2-31a's own wording ("created_at > P.confirmed_at") double-counts a row P
    # itself raised close to ITS OWN confirm (created_at just after P.confirmed_at,
    # long before D's) as "raised by D" - `_settle_row_in_place` never touches
    # `created_at`, so a row D only SETTLED still carries a creation stamp from back
    # when P first raised it. What the step actually means is "created after P
    # stopped being the active decision", which is D's OWN confirm - the same
    # instant `attach()` stamps as `P.superseded_at` - so both branches collapse to
    # one formula: D's own confirm, less a grace window for the same clock-skew the
    # "no P" fallback already names (a raise and its confirm land microseconds apart
    # inside one transaction). `decision.confirmed_at` is a naive datetime that is
    # already UTC - every connection in this app sets `-c timezone=utc`
    # (`app/database.py`) - so subtracting a bare `timedelta` here is safe without a
    # tzinfo mismatch.
    #
    # AC-R2-19b: WHY THE GRACE WINDOW IS NOT MERELY CLOCK SKEW, and why it is not enough
    # on its own. `order_inquiry_rows.created_at` is `server_default=func.now()`, and
    # Postgres' `now()` is the TRANSACTION's start, not the statement's - while
    # `confirmed_at` is a `datetime.utcnow()` read in Python partway through that same
    # transaction. So a row this confirm RAISED is routinely stamped BEFORE its own
    # decision's `confirmed_at` (prod SO314594: rows at 22:54:29.118, decision at
    # 22:54:29.932), and without the window step (a) would miss every one of them. That
    # also means the window BREAKS on a transaction that runs longer than it: a planning-
    # change apply walking many orders can take minutes, and a row it raised would then
    # sit further back than 60s, be read as pre-existing, and be repointed (to NULL, with
    # no prior) instead of deleted - left alive as a decision-less live row, which is
    # exactly the state AC-R2-19 traced the phantom "Confirmed" pill to.
    #
    # `raised_stamps` closes that without guessing: every row written in the SAME
    # transaction as its decision carries the SAME `now()`, and `so_supply_decisions.
    # created_at` is that identical default, so "raised by this confirm" is an EXACT
    # equality. Verified against real data (prod copy, 18 Sep): all 61 rows carrying a
    # `supply_decision_id` match their decision's own `created_at` to the microsecond. A
    # row this confirm only SETTLED cannot collide with it - it was created in an earlier
    # transaction, and `_settle_row_in_place` never touches `created_at`.
    #
    # The window stays as the outer bound rather than being replaced: it is what catches
    # a row raised by a legacy path that set `created_at` in Python rather than letting
    # the default fire.
    cutoff = decision.confirmed_at - timedelta(seconds=_WINDOW_SECONDS)
    raised_stamps = {d.created_at for d in touched_decisions if d.created_at is not None}

    oi_service = ProjectOrderInquiryService(db)
    removed_lines: List[Dict[str, Any]] = []
    restored_lines: List[Dict[str, Any]] = []

    # S3: EVERY touched decision's own rows, not just D's own - the donor's own
    # re-issue raises/settles rows under ITS OWN `supply_decision_id`, never D's.
    revision_by_decision_id: Dict[str, int] = {d.id: d.revision_no for d in touched_decisions}
    touched_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.supply_decision_id.in_(touched_decision_ids))
        .all()
    )
    raised_rows = [
        row
        for row in touched_rows
        if row.created_at
        and (row.created_at > cutoff or row.created_at in raised_stamps)
    ]
    raised_ids = {row.id for row in raised_rows}
    remaining_rows = [row for row in touched_rows if row.id not in raised_ids]

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
    # repoint to P (or NULL, no P). S2 (review round 1): `changed_at` alone misses
    # a row settled while still `ACK_AWAITING` - `_settle_row_in_place` never
    # stamps `changed_at` for one (a row nobody has acknowledged says nothing to
    # restore a timestamp FROM), even though `previous_qty`/`previous_delivery_
    # date` are written unconditionally on every real change. A row carrying
    # either previous value at all is judged the same as one inside the window;
    # `changed_at` only widens which OTHERWISE-untouched rows also qualify.
    for row in remaining_rows:
        in_window = (
            row.changed_at is not None
            and abs((row.changed_at - decision.confirmed_at).total_seconds()) <= _WINDOW_SECONDS
        )
        has_previous = row.previous_qty is not None or row.previous_delivery_date is not None
        # S3: THIS row's own owning decision - a donor row touched here was
        # settled by the donor's OWN re-issue, not by D, so both the note and
        # the repoint below name/use that decision, never D's unconditionally.
        own_decision_id = row.supply_decision_id
        own_revision_no = revision_by_decision_id.get(own_decision_id, decision.revision_no)
        if in_window or has_previous:
            stamp = f"restored by reconstructed undo of revision {own_revision_no}"
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
        # AC-R2-19b: NULL here means "belonged to no revision", and that is the honest
        # answer for every row that reaches this line with no prior to point at, because
        # every such row was already decision-less before this confirm settled it. Three
        # writers make them and none sets `supply_decision_id`: the OI sheet import
        # (#875, "Migrated from order inquiry sheet ..."), `derive_for_book_change` (the
        # planning-change reaction - prod SO314594 carries three of those, noted "Was
        # 2026-09-01"), and `derive_for_amendment` (an OCN's own exception rows). A row
        # this confirm RAISED never reaches here at all: step (a) above took it, by the
        # transaction-stamp equality documented at `raised_stamps`. So the one shape the
        # AC forbids - a row left alive claiming a revision that no longer exists, or
        # silently promoted to "decides the line" (`demand.live_inquiry_core_line_ids`)
        # because a `SET NULL` cascade emptied its pointer - cannot be produced here.
        row.supply_decision_id = prior_by_decision_id.get(own_decision_id)
    db.flush()

    if inquiry_ids and revision_nos:
        # (c) rows D (or a same-transaction donor decision) cancelled (a plain
        # supersede that confirm wrote): reinstated to raised. S3: scoped across
        # EVERY touched order's own inquiry, not just D's own order, and ANY of
        # the touched decisions' own revision numbers - the donor's cancelled
        # row carries no `supply_decision_id` pointing at D at all, only a note
        # naming the DONOR's OWN revision number, never D's.
        superseded_notes = [f"Superseded by revision {n}" for n in revision_nos]
        for row in (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id.in_(inquiry_ids),
                OrderInquiryRow.state == INQUIRY_CANCELLED,
                OrderInquiryRow.note.in_(superseded_notes),
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

        # (d) rows D (or a donor decision) released (redirected to the pool):
        # flagged back, same multi-order/multi-revision scope as (c).
        released_markers = [f"released at revision {n}" for n in revision_nos]
        for row in (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id.in_(inquiry_ids),
                OrderInquiryRow.redirected_to_pool.is_(True),
            )
            .all()
        ):
            if not (row.note and any(marker in row.note for marker in released_markers)):
                continue
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

    # (e) allocations and transfers of D AND every touched sibling decision (S3).
    # Loaded and disposed of one ORM object at a time - like every other write in
    # this function - rather than a bulk `Query.delete()`/`.update()`: a bulk
    # operation does not give the SAME object already sitting in THIS session's
    # identity map (a caller's own fixture reference, say) the ordinary `db.
    # delete()` lifecycle, and a later attribute read on it after commit raises
    # `DetachedInstanceError`/`ObjectDeletedError` instead of the clean "gone" a
    # plain `db.delete()` leaves behind.
    for allocation in (
        db.query(SOLineAllocation)
        .filter(SOLineAllocation.decision_id.in_(touched_decision_ids))
        .all()
    ):
        db.delete(allocation)
    for transfer in (
        db.query(StockTransfer)
        .filter(
            StockTransfer.supply_decision_id.in_(touched_decision_ids),
            StockTransfer.state == TRANSFER_PROPOSED,
        )
        .all()
    ):
        db.delete(transfer)
    # A transfer D's own confirm (or a donor's own same-transaction decision)
    # CANCELLED (superseding an earlier revision's proposal) has its `supply_
    # decision_id` cleared to `None` at cancel time - the same pattern a cancelled
    # `order_inquiry_rows` row follows (c) - so this one is found by `cancelled_
    # reason` text, matched against ANY touched decision's own revision number,
    # scoped to EVERY touched order (S3), never `supply_decision_id = D.id` alone.
    transfer_cancelled_reasons = [f"Superseded by revision {n}" for n in revision_nos]
    for transfer in (
        db.query(StockTransfer)
        .filter(
            StockTransfer.project_sales_order_id.in_(pso_ids),
            StockTransfer.state == TRANSFER_CANCELLED,
            StockTransfer.cancelled_reason.in_(transfer_cancelled_reasons),
        )
        .all()
        if pso_ids
        else []
    ):
        transfer.state = TRANSFER_PROPOSED
        # Repointed to THIS TRANSFER'S OWN order's own prior decision - a donor's
        # cancelled transfer must never be repointed to the BORROWER's own prior
        # (cross-order corruption), even though both share this same reconstruct
        # call.
        transfer.supply_decision_id = prior_by_pso_id.get(transfer.project_sales_order_id)
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
    # Read before the DELETE below: `_return_batch_to_pending` (step g) needs the confirm
    # instant for its legacy fallback, and the row is gone by the time it runs.
    confirmed_at = decision.confirmed_at
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

    # (g) AC-R2-19a: a revision minted by a PLANNING-CHANGE APPLY takes its batch back
    # to `pending` with it, exactly as the journal undo does by replaying the
    # `planning_change_*` rows it recorded. Without it the batch stayed `applied` while
    # the revision it produced was gone, so the board kept reading the drifted lines as
    # decided (`reopened_by_change` is a PENDING-row fact) and there was no way left to
    # re-decide them. Runs after the delete above: the decision is already gone and both
    # facts this needs - the order and the revision number - were read off it before.
    _return_batch_to_pending(db, order, revision_no, confirmed_at)

    # nothing here ever writes an `SOSupplyDecisionDraft` row.

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
