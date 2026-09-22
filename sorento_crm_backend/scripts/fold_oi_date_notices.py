#!/usr/bin/env python3
"""Fold a duplicate ADVANCE/DELAY notice back into the buy row it stood beside.

WHY THIS EXISTS
---------------
S2 (`PLAN-board-oi-mechanical-22sep.md`, AC-B2-1..9): before that fix, a date move on a
line `_settle_row_in_place` could not read as one instruction - two still-owed rows, a
lone placed row with no link, or every row already actioned - left the line's own buy
row(s) with no date stamp at all AND raised a second ADVANCE/DELAY row beside them saying
the same thing. Every OI raised on prod before the fix can carry that duplicate; nothing
re-runs the confirm for them, so this backfill folds it by hand.

WHAT IT DOES
------------
Finds every LIVE (non-cancelled) `ADVANCE`/`DELAY` row whose `so_line_id` also carries a
LIVE (non-cancelled) `ORDER`/`ORDER_BACK` row - the shape the fix now prevents. For each:

* the notice's own note is read for a `Was <date>` the old code wrote when it raised it
  (`_oi_demand_rows`'s pre-fix note, `f"Was {from_date}"` with an ISO date) - a note with
  no parseable date is left alone and counted separately, never guessed at;
* `--apply` cancels the notice, appends "Folded into the buy row by script, <today>" to
  its own note, and stamps the buy row with `previous_delivery_date` (the parsed date),
  `changed_at` (now) and a "Was <qty> on <date>" note - the same shape `_stamp_date_move`
  writes for a fresh date move, so the Lines tab's Was/Now table reads either one alike.

SAFETY / IDEMPOTENCY
---------------------
JOIN-based and re-runnable per the repo's backfill doctrine: the match is "a LIVE notice
still stands beside a LIVE buy row on the same line", so a pair this script already folded
- the notice is now cancelled - no longer matches and a second run reports nothing.

`--dry-run` is the DEFAULT. Nothing is written without `--apply`.

Run from sorento_crm_backend/:
    venv/bin/python scripts/fold_oi_date_notices.py
    venv/bin/python scripts/fold_oi_date_notices.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.project_so import (
    INQUIRY_CANCELLED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import _dec, _qty_str

#: `_oi_demand_rows`'s own pre-fix note (`f"Was {from_date}"`, `from_date` an ISO
#: `date.isoformat()` string) - the only shape a notice this script targets ever carries.
_WAS_DATE_RE = re.compile(r"Was (\d{4}-\d{2}-\d{2})")


def _parse_was_date(note: Optional[str]) -> Optional[date]:
    if not note:
        return None
    match = _WAS_DATE_RE.search(note)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _live_notice_buy_pairs(
    db: Session,
) -> List[Tuple[OrderInquiryRow, OrderInquiryRow, Optional[str]]]:
    """Every (notice, buy row, OI number), oldest notice first.

    Two queries rather than a join across two aliases of the same table on `so_line_id`:
    a line may carry more than one live buy row (AC-B2-5's own shape), and the FIRST one
    raised is what the notice's own duplicate stood beside.
    """
    notices = (
        db.query(OrderInquiryRow, OrderInquiry.inquiry_no)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(
            OrderInquiryRow.verb.in_((IV_ADVANCE, IV_DELAY)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.so_line_id.isnot(None),
        )
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )
    if not notices:
        return []
    line_ids = {notice.so_line_id for notice, _oi_number in notices}
    buy_rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id.in_(line_ids),
            OrderInquiryRow.verb.in_((IV_ORDER, IV_ORDER_BACK)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )
    buy_row_by_line: Dict[str, OrderInquiryRow] = {}
    for buy_row in buy_rows:
        buy_row_by_line.setdefault(str(buy_row.so_line_id), buy_row)

    pairs: List[Tuple[OrderInquiryRow, OrderInquiryRow, Optional[str]]] = []
    for notice, oi_number in notices:
        buy_row = buy_row_by_line.get(str(notice.so_line_id))
        if buy_row is None:
            continue
        pairs.append((notice, buy_row, oi_number))
    return pairs


def _fold(db: Session, notice: OrderInquiryRow, buy_row: OrderInquiryRow, was_date: date) -> None:
    """`--apply`'s own write: cancel the notice, stamp the buy row it duplicated."""
    today = date.today().isoformat()
    notice.state = INQUIRY_CANCELLED
    notice.note = (
        f"{notice.note}; Folded into the buy row by script, {today}"
        if notice.note
        else f"Folded into the buy row by script, {today}"
    )
    buy_row.previous_delivery_date = was_date
    buy_row.changed_at = datetime.utcnow()
    stamp = f"Was {_qty_str(_dec(buy_row.qty))} on {was_date.isoformat()}"
    buy_row.note = f"{buy_row.note}; {stamp}" if buy_row.note else stamp
    db.flush()


def run(db: Session, *, apply: bool = False) -> Dict[str, Any]:
    """Report (and optionally perform) every fold. The caller commits."""
    pairs_out: List[Dict[str, Any]] = []
    folded = 0
    skipped_no_was = 0

    for notice, buy_row, oi_number in _live_notice_buy_pairs(db):
        was_date = _parse_was_date(notice.note)
        pairs_out.append(
            {
                "oi_number": oi_number,
                "item_code": notice.item_code,
                "qty": _qty_str(_dec(notice.qty)),
                "notice_date": (
                    notice.delivery_date.isoformat() if notice.delivery_date else None
                ),
                "buy_row_id": str(buy_row.id),
                "buy_row_date": (
                    buy_row.delivery_date.isoformat() if buy_row.delivery_date else None
                ),
            }
        )
        if was_date is None:
            skipped_no_was += 1
            print(
                f"  SKIPPED (no Was date): {oi_number or notice.order_inquiry_id} "
                f"{notice.item_code} - note: {notice.note!r}"
            )
            continue
        print(
            f"  {oi_number or notice.order_inquiry_id} {notice.item_code} "
            f"qty {_qty_str(_dec(notice.qty))} was {was_date.isoformat()} "
            f"-> buy row {buy_row.id} ({buy_row.delivery_date})"
        )
        if apply:
            _fold(db, notice, buy_row, was_date)
            folded += 1

    return {"pairs": pairs_out, "folded": folded, "skipped_no_was": skipped_no_was}


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
    # system / all-companies scope: this folds duplicates wherever they live.
    set_company_scope(db, None)

    try:
        print(
            "Duplicate ADVANCE/DELAY notices beside a live buy row "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summary = run(db, apply=apply)
        if apply:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:                {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"pairs examined:      {len(summary['pairs'])}")
        print(f"folded:              {summary['folded']}")
        print(f"skipped, no Was date:{summary['skipped_no_was']}")
        if not apply and summary["pairs"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
