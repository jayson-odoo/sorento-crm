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
LIVE (non-cancelled) `ORDER`/`ORDER_BACK` row - the shape the fix now prevents. A line may
carry MORE THAN ONE live buy row (AC-B2-5's own shape, round 3): every one of them is a
candidate, not only the first ever raised - `_stamp_date_move` itself stamps every live
buy row of a line the same way, so the fold reads a duplicate the same way it reads a
fresh one. For each notice:

* the notice's own note is read for a `Was <date>` the old code wrote when it raised it
  (`_oi_demand_rows`'s pre-fix note, `f"Was {from_date}"` with an ISO date) - a note with
  no parseable date is left alone and counted separately, never guessed at;
* a candidate buy row is folded ONLY when its OWN `delivery_date` still equals that parsed
  `Was` date (round 3) - the row demonstrably still says the old thing. A row already
  sitting somewhere else (moved by some other means since the notice was raised) is left
  untouched and counted separately: the fold never moves a row backwards, and never
  guesses which of a line's several rows the notice was about;
* `--apply` stamps every matching buy row with `delivery_date` (the NOTICE's own date),
  `previous_delivery_date` (the parsed date) and a "Was <qty> on <date>" note - the same
  shape `_stamp_date_move` writes for a fresh date move, so the Lines tab's Was/Now table
  reads either one alike - then cancels the notice once, appending "Folded into the buy
  row by script, <today>" to its own note. A notice with NO matching row (every candidate
  already moved elsewhere) is left live and uncancelled, so a person can still see and
  resolve it by hand. The HANDSHAKE follows the same gate that method reads (owner
  ruling, 22 Sep): `changed_at` is stamped and `ack_state` drops to `changed` only on a
  row purchasing had already acknowledged; a row still `awaiting` keeps its handshake and
  a NULL `changed_at`.

  The `delivery_date` hand-over is the point of the whole fold (review round, 22 Sep):
  the NOTICE is the only row that ever carried the new date, so cancelling it without
  moving the buy row would delete the date move rather than fold it, leaving the buy row
  reading as though the book had never moved. A notice carrying NO date of its own has
  nothing to hand over and is left alone and counted, the same rule as a missing `Was`.

SAFETY / IDEMPOTENCY
---------------------
JOIN-based and re-runnable per the repo's backfill doctrine: the match is "a LIVE notice
still stands beside a LIVE buy row on the same line, on the date the notice's own `Was`
names", so a pair this script already folded - the buy row moved off the Was date, the
notice is now cancelled - no longer matches and a second run reports nothing for it.

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
    ACK_ACKNOWLEDGED,
    ACK_CHANGED,
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
) -> List[Tuple[OrderInquiryRow, List[OrderInquiryRow], Optional[str]]]:
    """Every (notice, ALL its live buy rows, OI number), oldest notice first.

    Two queries rather than a join across two aliases of the same table on `so_line_id`.
    Round 3: a line may carry more than one live buy row (AC-B2-5's own shape) - every one
    of them is returned, not only the first ever raised; the caller decides, per row,
    whether it still matches what the notice announced.
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
    buy_rows_by_line: Dict[str, List[OrderInquiryRow]] = {}
    for buy_row in buy_rows:
        buy_rows_by_line.setdefault(str(buy_row.so_line_id), []).append(buy_row)

    pairs: List[Tuple[OrderInquiryRow, List[OrderInquiryRow], Optional[str]]] = []
    for notice, oi_number in notices:
        rows = buy_rows_by_line.get(str(notice.so_line_id))
        if not rows:
            continue
        pairs.append((notice, rows, oi_number))
    return pairs


def _stamp_buy_row(buy_row: OrderInquiryRow, notice: OrderInquiryRow, was_date: date) -> None:
    """`--apply`'s own write on ONE matching buy row: the notice's own date handed over,
    the old one kept as Was - the same shape `_stamp_date_move` writes for a fresh move."""
    # The notice's own date is the new one; the buy row is still on the old.
    if notice.delivery_date and buy_row.delivery_date != notice.delivery_date:
        buy_row.delivery_date = notice.delivery_date
    buy_row.previous_delivery_date = was_date
    stamp = f"Was {_qty_str(_dec(buy_row.qty))} on {was_date.isoformat()}"
    buy_row.note = f"{buy_row.note}; {stamp}" if buy_row.note else stamp
    # The SAME handshake gate `_stamp_date_move` reads (owner ruling, 22 Sep): a row
    # purchasing had already taken on has just been restated under them, so it goes back
    # to To confirm and stamps WHEN - `changed_at` answers "when CS last amended a row
    # purchasing had already acknowledged" (`OrderInquiryRow.changed_at`). A row still
    # AWAITING keeps its handshake and its NULL `changed_at`: there is no acknowledgement
    # to have amended under, and asking purchasing to re-read something they never read is
    # not a fold. The date and the two `previous_*` columns land either way, so the
    # Was / Now table reads the folded row the same whichever side of the gate it is on.
    if buy_row.ack_state in (ACK_ACKNOWLEDGED, ACK_CHANGED):
        buy_row.changed_at = datetime.utcnow()
        buy_row.ack_state = ACK_CHANGED


def _cancel_notice(notice: OrderInquiryRow) -> None:
    """The notice's own half of a fold, done ONCE per notice - after every matching buy
    row of its line has been stamped, never before, and never at all when nothing
    matched (round 3): a notice left live is a notice a person can still see."""
    today = date.today().isoformat()
    notice.state = INQUIRY_CANCELLED
    notice.note = (
        f"{notice.note}; Folded into the buy row by script, {today}"
        if notice.note
        else f"Folded into the buy row by script, {today}"
    )


def run(db: Session, *, apply: bool = False) -> Dict[str, Any]:
    """Report (and optionally perform) every fold. The caller commits."""
    pairs_out: List[Dict[str, Any]] = []
    folded = 0
    skipped_no_was = 0
    skipped_no_notice_date = 0
    skipped_row_not_on_was_date = 0

    for notice, buy_rows, oi_number in _live_notice_buy_pairs(db):
        was_date = _parse_was_date(notice.note)
        for buy_row in buy_rows:
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
        if notice.delivery_date is None:
            # Nothing to hand over: the notice is the only row carrying the new date.
            skipped_no_notice_date += 1
            print(
                f"  SKIPPED (notice has no delivery date): "
                f"{oi_number or notice.order_inquiry_id} {notice.item_code}"
            )
            continue
        # Round 3: fold onto EVERY live buy row of the line, but only the ones that
        # still sit on the date the notice's own "Was" names - a row already moved
        # elsewhere is left alone and counted, never moved backwards or guessed at.
        any_folded = False
        for buy_row in buy_rows:
            if buy_row.delivery_date != was_date:
                skipped_row_not_on_was_date += 1
                print(
                    f"  SKIPPED (buy row not on the notice's Was date): "
                    f"{oi_number or notice.order_inquiry_id} {notice.item_code} "
                    f"buy row {buy_row.id} on "
                    f"{buy_row.delivery_date.isoformat() if buy_row.delivery_date else None}, "
                    f"expected {was_date.isoformat()}"
                )
                continue
            # AC-B2-11: the notice's OWN delivery date is on the line, so a dry run can
            # be read for where each buy row is about to be MOVED to, not only where it
            # sits.
            print(
                f"  {oi_number or notice.order_inquiry_id} {notice.item_code} "
                f"qty {_qty_str(_dec(buy_row.qty))} was {was_date.isoformat()} "
                f"notice date {notice.delivery_date.isoformat()} "
                f"-> buy row {buy_row.id} ({buy_row.delivery_date})"
            )
            if apply:
                _stamp_buy_row(buy_row, notice, was_date)
                folded += 1
                any_folded = True
        if apply and any_folded:
            _cancel_notice(notice)

    if apply:
        db.flush()

    return {
        "pairs": pairs_out,
        "folded": folded,
        "skipped_no_was": skipped_no_was,
        "skipped_no_notice_date": skipped_no_notice_date,
        "skipped_row_not_on_was_date": skipped_row_not_on_was_date,
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
        print(f"skipped, no notice date:{summary['skipped_no_notice_date']}")
        print(
            f"skipped, buy row not on Was date:{summary['skipped_row_not_on_was_date']}"
        )
        if not apply and summary["pairs"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
