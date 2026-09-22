#!/usr/bin/env python3
"""One-off: flip an ORDER row the importer's own history-close bug turned into
`actioned` back to ORDER_BACK / raised, when the uploaded sheet's row reads ORDER BACK.

`PLAN-oi-order-back-not-capped.md` S4, R4/R5 (owner ruling 22 Sep 2026, SO417310 /
MKT5529SS-DIY). Before S1/S3 of that lane landed, the reader only read ORDER BACK from the
delivery-date cell (missing the remark-cell case, R1) and `_close_history` stamped
`actioned` on ANY raised row against a delivered line, ORDER_BACK included (R3). Together
that turned an order back CS wrote into a closed ORDER instruction the moment it was
uploaded - the picker hides the order, and `scm.committed_v` reads it as satisfied. The
fix in `app.services.scm.demand` / `project_order_inquiry_import_service` stops it
happening to a NEW upload; this script repairs what already shipped that way.

WHAT IT DOES
------------
Reads each `.xlsx` given on the command line with the SAME sheet reader the upload path
uses (`app.services.project_order_inquiry_reader.read_order_inquiry`), so a row is read as
ORDER BACK here exactly when it now would be on a fresh upload. For every such row it
looks up the matching `projects.order_inquiry_rows` row by walking the sheet's own
identity - SO number, item code, quantity, delivery date, stock location - through
`sales_orders.so_number` -> `projects.sales_orders.so_id` -> `projects.order_inquiries` ->
`projects.order_inquiry_rows`.

A candidate only exists among rows the IMPORTER, not a person, closed: `verb = 'ORDER'`,
`state = 'actioned'`. Whether the importer (rather than a person) closed it is read off
the clock: the importer stamps `actioned_at` from the SAME `now` it stamps the header's
own `raised_at` with (`_close_history`'s caller), so an importer-closed row's `actioned_at`
sits within 60 seconds of `order_inquiries.raised_at`. Rows imported before the S5a
timezone fix (`project_order_inquiry_import_service.py`, `_now()`) wrote a naive MYT wall
clock instead of naive UTC for one of the two writers, an 8-hour skew - so the window also
accepts `raised_at + 8h`, which is what prod row bee581f3 (SO417310 / MKT5529SS-DIY, raised
03:19:03, actioned 11:19:23) shows. Anything else is a person's own action and is never
touched (R4).

A flip sets: `verb = 'ORDER_BACK'`, `state = 'raised'`, `actioned_by = NULL`,
`actioned_at = NULL`, and the row's own inquiry header `state = 'raised'`.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT and writes nothing: every candidate is read and classified, and
the row is only mutated `if apply` - a dry run never touches an ORM attribute, so there is
nothing to roll back, and nothing to undo the caller's own transaction with either.
`--apply` commits once at the end. A second run over rows this script already flipped
reports them `unmatched` (there is no more
`verb = 'ORDER'` row at that identity to match), never a double-flip.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_order_back_rows.py book1.xlsx
    venv/bin/python scripts/backfill_order_back_rows.py --apply book1.xlsx book2.xlsx
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import set_company_scope
from app.models.order import SalesOrder
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.services.project_order_inquiry_reader import read_order_inquiry

#: The importer's write of `actioned_at` and the header's own `raised_at` come off the
#: same `now` (`project_order_inquiry_import_service.py`), so an exact match is the
#: ordinary case. A few seconds of slack for clock/roundtrip noise, never a whole day.
_CLOSE_WINDOW = timedelta(seconds=60)

#: The S5a timezone bug's own skew (naive MYT stored where naive UTC belonged), still
#: sitting in every row imported before that fix landed.
_MYT_SKEW = timedelta(hours=8)


def _dec(value: Any) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


def _is_importer_closed(actioned_at, raised_at) -> bool:
    """Whether this row's `actioned_at` carries the importer's own clock rather than a
    person's - the two windows described in the module docstring."""
    if actioned_at is None or raised_at is None:
        return False
    delta = abs(actioned_at - raised_at)
    if delta <= _CLOSE_WINDOW:
        return True
    return abs(actioned_at - (raised_at + _MYT_SKEW)) <= _CLOSE_WINDOW


def _match(db, entry) -> Optional[tuple]:
    """The one `(OrderInquiryRow, OrderInquiry)` an importer-closed ORDER row at this
    sheet row's identity, if there is one. `None` when nothing matches - unmatched, not
    created (AC-OB-16)."""
    q = (
        db.query(OrderInquiryRow, OrderInquiry)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .join(ProjectSalesOrder, ProjectSalesOrder.id == OrderInquiry.project_sales_order_id)
        .join(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
        .filter(SalesOrder.so_number == entry.so_number)
        .filter(OrderInquiryRow.item_code == entry.item_code)
        .filter(OrderInquiryRow.verb == IV_ORDER)
        .filter(OrderInquiryRow.state == INQUIRY_ACTIONED)
    )
    qty = _dec(entry.qty)
    if qty is not None:
        q = q.filter(OrderInquiryRow.qty == qty)
    if entry.location:
        q = q.filter(OrderInquiryRow.stock_location == entry.location)
    else:
        q = q.filter(OrderInquiryRow.stock_location.is_(None))
    if entry.delivery_date is not None:
        q = q.filter(OrderInquiryRow.delivery_date == entry.delivery_date)
    else:
        q = q.filter(OrderInquiryRow.delivery_date.is_(None))
    return q.order_by(OrderInquiryRow.id.asc()).first()


def run(db, xlsx_paths: Sequence[str], apply: bool) -> List[Dict[str, Any]]:
    """One dict per sheet row that reads ORDER BACK, across every book given. Never
    raises on a bad file - a row from a file that could not be read is simply absent,
    the same as the upload path's own `problems` list."""
    results: List[Dict[str, Any]] = []
    for path in xlsx_paths:
        with open(path, "rb") as fh:
            data = fh.read()
        parsed = read_order_inquiry(data)
        for entry in parsed.rows:
            if not entry.order_back:
                continue
            common = {
                "so_number": entry.so_number,
                "item_code": entry.item_code,
                "qty": entry.qty,
                "stock_location": entry.location,
            }
            match = _match(db, entry)
            if match is None:
                results.append({**common, "action": "unmatched"})
                continue
            row, inquiry = match
            if _is_importer_closed(row.actioned_at, inquiry.raised_at):
                if apply:
                    row.verb = IV_ORDER_BACK
                    row.state = INQUIRY_RAISED
                    row.actioned_by = None
                    row.actioned_at = None
                    inquiry.state = INQUIRY_RAISED
                results.append({**common, "action": "flipped"})
            else:
                results.append({**common, "action": "skipped_person_actioned"})
    # A dry run mutates nothing above (`if apply:` gates every write), so there is
    # nothing to roll back - and rolling back anyway would discard the CALLER's own
    # uncommitted work too, which is exactly the transaction this session is on.
    if apply:
        db.commit()
    return results


def main(argv: Optional[Sequence[str]] = None, db=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "xlsx", nargs="+", help="one or more Order Inquiry sheets to re-read",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the changes; the default is a dry run",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)

    owns_db = db is None
    if db is None:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        # A script has no request and no principal, so the session scope would be UNSET
        # (fail-closed, 0 rows) - the same reason `backfill_oi_follow_book.py` sets it.
        # The match walks so_number -> projects.sales_orders -> order_inquiries itself, so
        # no per-company narrowing is needed here.
        set_company_scope(db, None)

        print(
            "Order Inquiry rows read as ORDER BACK "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        results = run(db, args.xlsx, apply)

        counts: Dict[str, int] = {}
        for entry in results:
            counts[entry["action"]] = counts.get(entry["action"], 0) + 1
            print(
                f"  [{entry['action']}] SO {entry['so_number']} / {entry['item_code']} "
                f"qty {entry['qty']} @ {entry['stock_location'] or '(no location)'}"
            )

        print("\n=== summary ===")
        print(f"mode:                    {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"rows read as ORDER BACK: {len(results)}")
        print(f"flipped:                 {counts.get('flipped', 0)}")
        print(f"skipped (person actioned): {counts.get('skipped_person_actioned', 0)}")
        print(f"unmatched:               {counts.get('unmatched', 0)}")
        if not apply and counts.get("flipped"):
            print("\nRe-run with --apply to write these changes.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
