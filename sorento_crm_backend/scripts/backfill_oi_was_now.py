#!/usr/bin/env python3
"""Stamp Was/Now on a fresh Buy row raised beside a used row, before PR #992 could.

WHY THIS EXISTS
----------------
PR #992 (merged, deployed 17 Sep 2026) made a confirm that releases a received row
(``order_inquiry_rows.redirected_to_pool = true``, shown "used") stamp the fresh ORDER
row it raises with ``previous_qty`` / ``previous_delivery_date`` and a note "Replaces
<qty> used; <document> received <date|in full> into <location>"
(``ProjectOrderInquiryService._redirect_row_if_received`` /
``_release_fragment``, ``app/services/project_order_inquiry_service.py``), and
suppress the DELAY / ADVANCE reaction row purchasing would otherwise see beside it.

Rows written BEFORE that deploy carry the used row's own "released at revision N" note
but never got a Was/Now on the fresh row raised beside them, and their DELAY/ADVANCE
row still sits there. This is the one-off backfill for those.

WHAT IT DOES
------------
For each ``order_inquiry_rows`` row R with ``redirected_to_pool = true`` whose note
carries "released at revision N" (the exact fragment
``_redirect_row_if_received`` writes):

1. finds the ``so_supply_decisions`` row for R's own order at ``revision_no = N``,
2. finds the ONE fresh ORDER/ORDER_BACK row F on the same SO line, pointing at that
   decision, still carrying no Was/Now (``previous_qty IS NULL``) - skipping (and
   printing why) when there is none or more than one,
3. stamps F's ``previous_qty`` / ``previous_delivery_date`` from R and appends the same
   "Replaces <qty> used; ..." note the live confirm would have written - reusing
   ``ProjectOrderInquiryService._release_fragment`` rather than re-deriving its wording,
4. cancels every DELAY/ADVANCE row on the same line, still ``raised`` with no supply
   decision of its own, written within five minutes of F - the reaction the live confirm
   would have suppressed - and appends why to its note.

SAFETY / IDEMPOTENCY
---------------------
Re-runnable: step 2's own ``previous_qty IS NULL`` filter is the match, so a row this
script already stamped no longer matches and a second run reports nothing further to do.

``--dry-run`` is the DEFAULT. Nothing is written without ``--apply``.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_oi_was_now.py
    venv/bin/python scripts/backfill_oi_was_now.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.project_so import (
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    SOSupplyDecision,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService, _dec, _qty_str

#: The exact fragment `_redirect_row_if_received` writes on the USED row's own note
#: (`app/services/project_order_inquiry_service.py`). Anything without it names no
#: revision to look the fresh row up by, and is skipped.
_REVISION_RE = re.compile(r"released at revision (\d+)")

#: A fresh ORDER row and the reaction row it should have suppressed are written by two
#: separate calls in the same confirm - close together, never far apart. Five minutes is
#: a generous window either side, not a measured gap.
_REACTION_WINDOW = timedelta(minutes=5)

_OWNED_VERBS = (IV_ORDER, IV_ORDER_BACK)
_FRESH_STATES = (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED)
_REACTION_VERBS = (IV_DELAY, IV_ADVANCE)

_BACKFILL_NOTE = (
    "Superseded by revision {revision_no} "
    "(backfill 18 Sep 2026: the confirm restated the line)"
)


@dataclass
class Repair:
    """One used row matched to the one fresh row it should have stamped."""

    used_row_id: str
    fresh_row_id: str
    revision_no: int
    order_label: str
    item_code: Optional[str]

    def describe(self) -> str:
        item = f" {self.item_code}" if self.item_code else ""
        return (
            f"{self.order_label}{item}: revision {self.revision_no}, "
            f"used row {self.used_row_id} -> fresh row {self.fresh_row_id}"
        )


def _order_label(db: Session, order_inquiry_id: str) -> str:
    inquiry = db.query(OrderInquiry).filter(OrderInquiry.id == order_inquiry_id).one_or_none()
    if inquiry is None:
        return "unknown order"
    pso = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == inquiry.project_sales_order_id)
        .one_or_none()
    )
    if pso is None:
        return "unknown order"
    return pso.autocount_doc_no or pso.provisional_ref


def _used_rows(db: Session) -> List[OrderInquiryRow]:
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.redirected_to_pool.is_(True))
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )


def _fresh_row_for(db: Session, used_row: OrderInquiryRow, revision_no: int) -> Optional[OrderInquiryRow]:
    inquiry = (
        db.query(OrderInquiry).filter(OrderInquiry.id == used_row.order_inquiry_id).one_or_none()
    )
    if inquiry is None:
        print(f"  SKIP used row {used_row.id}: its order inquiry header is gone")
        return None
    decision = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == inquiry.project_sales_order_id,
            SOSupplyDecision.revision_no == revision_no,
        )
        .one_or_none()
    )
    if decision is None:
        print(
            f"  SKIP used row {used_row.id}: no revision {revision_no} decision on its order"
        )
        return None
    candidates = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == used_row.so_line_id,
            OrderInquiryRow.supply_decision_id == decision.id,
            OrderInquiryRow.verb.in_(_OWNED_VERBS),
            OrderInquiryRow.state.in_(_FRESH_STATES),
            OrderInquiryRow.previous_qty.is_(None),
        )
        .all()
    )
    if len(candidates) != 1:
        print(
            f"  SKIP used row {used_row.id}: found {len(candidates)} unstamped fresh rows "
            f"for revision {revision_no} (need exactly 1)"
        )
        return None
    return candidates[0]


def _reaction_rows_for(db: Session, fresh_row: OrderInquiryRow) -> List[OrderInquiryRow]:
    lo = fresh_row.created_at - _REACTION_WINDOW
    hi = fresh_row.created_at + _REACTION_WINDOW
    return (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == fresh_row.so_line_id,
            OrderInquiryRow.verb.in_(_REACTION_VERBS),
            OrderInquiryRow.state == INQUIRY_RAISED,
            OrderInquiryRow.supply_decision_id.is_(None),
            OrderInquiryRow.created_at >= lo,
            OrderInquiryRow.created_at <= hi,
        )
        .all()
    )


def find_repairs(db: Session) -> List[Repair]:
    """Every used row still missing its fresh row's Was/Now, matched one-for-one.

    A used row with no "released at revision N" fragment, no matching revision, or
    not exactly one unstamped fresh row on its line is reported (never raised) and
    left out of the returned list - see `_fresh_row_for`.
    """
    repairs: List[Repair] = []
    for used_row in _used_rows(db):
        match = _REVISION_RE.search(used_row.note or "")
        if not match:
            continue
        revision_no = int(match.group(1))
        fresh_row = _fresh_row_for(db, used_row, revision_no)
        if fresh_row is None:
            continue
        repairs.append(
            Repair(
                used_row_id=str(used_row.id),
                fresh_row_id=str(fresh_row.id),
                revision_no=revision_no,
                order_label=_order_label(db, used_row.order_inquiry_id),
                item_code=used_row.item_code,
            )
        )
    return repairs


def apply_repair(db: Session, repair: Repair) -> int:
    """Stamp the fresh row and cancel its superseded DELAY/ADVANCE rows.

    Returns how many reaction rows were cancelled.
    """
    used_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == repair.used_row_id).one()
    fresh_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == repair.fresh_row_id).one()

    service = ProjectOrderInquiryService(db)
    fragment = service._release_fragment(used_row)
    release_text = "; ".join(
        [f"Replaces {_qty_str(_dec(used_row.qty))} used"] + ([fragment] if fragment else [])
    )
    fresh_row.note = f"{fresh_row.note}; {release_text}" if fresh_row.note else release_text
    fresh_row.previous_qty = used_row.qty
    fresh_row.previous_delivery_date = used_row.delivery_date

    cancelled = 0
    for reaction_row in _reaction_rows_for(db, fresh_row):
        print(
            f"    cancelling {reaction_row.verb} row {reaction_row.id} "
            f"(superseded by revision {repair.revision_no})"
        )
        reaction_row.state = INQUIRY_CANCELLED
        suffix = _BACKFILL_NOTE.format(revision_no=repair.revision_no)
        reaction_row.note = f"{reaction_row.note}; {suffix}" if reaction_row.note else suffix
        cancelled += 1

    db.flush()
    return cancelled


def run(db: Session, *, apply: bool) -> Dict[str, Any]:
    """Report (and optionally perform) every repair. The caller commits."""
    repairs = find_repairs(db)
    reaction_rows_cancelled = 0

    for repair in repairs:
        print(f"  {repair.describe()}")
        if apply:
            reaction_rows_cancelled += apply_repair(db, repair)

    return {
        "fresh_rows_stamped": len(repairs) if apply else 0,
        "fresh_rows_found": len(repairs),
        "reaction_rows_cancelled": reaction_rows_cancelled,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the changes. Without this the script only reports.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only (the default; accepted so a run can say so out loud).",
    )
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET,
    # which is fail-closed and would return no rows at all. `None` is the sanctioned
    # system / all-companies scope - every row this touches belongs to whichever
    # company its own order does, unaffected by the scope it was found under.
    set_company_scope(db, None)

    try:
        print(
            "Used rows missing their fresh row's Was/Now "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summary = run(db, apply=apply)
        if apply:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:                    {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"fresh rows found:        {summary['fresh_rows_found']}")
        print(f"fresh rows stamped:      {summary['fresh_rows_stamped']}")
        print(f"reaction rows cancelled: {summary['reaction_rows_cancelled']}")
        if not apply and summary["fresh_rows_found"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
