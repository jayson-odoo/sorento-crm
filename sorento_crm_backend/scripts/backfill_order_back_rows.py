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
(`_close_history` itself is retired entirely as of 23 Sep 2026, R2,
`PLAN-oi-order-rows-uncapped.md` - the candidate gate refuses a cancelled line before a
row is ever raised, so there is nothing left for it to close after the fact.)

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
TWO signals together, both narrower than either alone:

* The CLOCK - the importer stamps `actioned_at` from the SAME `now` it stamps the
  header's own `raised_at` with (`_close_history`'s caller, back when this script was
  written - the function itself is retired now, see above), so an importer-closed row's
  `actioned_at` sits within 60 seconds of `order_inquiries.raised_at`. Rows imported
  before the S5a timezone fix (`project_order_inquiry_import_service.py`, `_now()`) wrote
  a naive MYT wall clock instead of naive UTC for one of the two writers, an 8-hour skew -
  so the window ALSO accepts `raised_at + 8h`. Measured on PROD TODAY (22 Sep 2026), row
  bee581f3 (SO417310 / MKT5529SS-DIY) is `raised_at` 2026-09-20 03:19:03 UTC,
  `actioned_at` 11:19:23 - the 8h skew, not the exact match. (A reviewer measurement
  against the `0921` dev copy read `raised_at == actioned_at` for the same row; migration
  523's own backfill only moves a header's `raised_at` EARLIER - `LEAST(raised_at,
  min(row created_at))` - never later, so it cannot be what produced an equal reading on
  that copy. The likelier explanation is that the 0921 copy's `raised_at` was re-stamped
  by a LATER reconfirm sometime after 523 ran there. Prod is the source of truth for this
  script either way.) Anything outside both windows is a person's own later action and is
  never touched (R4).
* The PRINCIPAL - the importer stamps `actioned_by` with the SAME uploader it stamps the
  header's own `raised_by` with (one upload, one actor, both writes in the same
  transaction). So an importer-closed row also has `actioned_by == raised_by`; a
  purchasing user marking the row actioned by hand is a DIFFERENT principal from whoever
  uploaded the sheet, even if their own click happened to land inside the clock window.

A flip sets: `verb = 'ORDER_BACK'`, `state = 'raised'`, `actioned_by = NULL`,
`actioned_at = NULL`, and the row's own inquiry header `state = 'raised'`.

BLANK SHEET CELLS
------------------
A blank delivery-date or stock-location cell on today's re-read is matched against the
SAME fallback the importer itself used when it first wrote the row
(`project_order_inquiry_import_service.py`, `raise_row`, ~:2771/:2772): the row's own core
sales-order line's `required_date` / warehouse code, reached through
`OrderInquiryRow.so_line_id` -> the mirror line -> `core_sales_order_line_id`. A blank
cell matches NULL (no core line, or the core line itself carries none) or that fallback -
never NULL alone, or a row the importer legitimately created with a fallback value would
read as a mismatch today.

COMPANY SCOPE
--------------
`so_number` is unique per company, not globally (`uq_sales_orders_company_so_number`), so
the SAME number can name two different orders in two different companies. `--company
<code>` narrows the match to one company outright. Without it, a dry run still lists every
company a candidate SO number resolves to (each row carries its own `company_code`) so a
human can see the ambiguity before choosing - but `--apply` REFUSES outright the moment
any sheet row's SO number resolves to more than one company, printing the ambiguous
numbers and exiting 2, rather than guessing which company's row to flip.

DEDUPE
-------
Two sheet rows that both resolve to the SAME `order_inquiry_rows` identity (a duplicated
line on the sheet, or two books repeating one row) dedupe on BOTH a dry run and `--apply`,
keyed on the row's own matching identity (company, SO number, item, qty, delivery date,
location) rather than re-querying a second time - a second `_match()` call after a flip
would see the row's now-`ORDER_BACK` verb and answer `unmatched`, which is a true
statement about the query but a misleading one about what happened, and the row is never
re-entered into the mutation branch either way. On a dry run the repeat is reported ONCE -
a reviewer reading the printed list is asking "which rows will move", not "how many sheet
cells named one". On `--apply` the repeat IS reported, labelled `already_flipped` when the
first occurrence flipped the row (so the printed count of sheet rows still matches the
uploaded file), or the same label the first occurrence got otherwise.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT and writes nothing: every candidate is read and classified, and
the row is only mutated `if apply` - a dry run never touches an ORM attribute, so there is
nothing to roll back, and nothing to undo the caller's own transaction with either.
`--apply` commits once at the end, or refuses before touching anything at all (the company
ambiguity check above). A second run over rows this script already flipped reports them
`unmatched` (there is no more `verb = 'ORDER'` row at that identity to match), never a
double-flip.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_order_back_rows.py book1.xlsx
    venv/bin/python scripts/backfill_order_back_rows.py --apply --company SRT book1.xlsx
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

from sqlalchemy import func, or_

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.project_order_inquiry_reader import read_order_inquiry


class AmbiguousCompanyError(Exception):
    """`--apply` with no `--company` and a sheet SO number that resolves to more than one
    company - see the module's COMPANY SCOPE section."""

    def __init__(self, so_numbers):
        self.so_numbers = sorted(so_numbers)
        super().__init__(
            "SO number(s) exist in more than one company - re-run with --company <code>: "
            + ", ".join(self.so_numbers)
        )


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
    person's - the two windows described in the module docstring's CLOCK bullet."""
    if actioned_at is None or raised_at is None:
        return False
    delta = abs(actioned_at - raised_at)
    if delta <= _CLOSE_WINDOW:
        return True
    return abs(actioned_at - (raised_at + _MYT_SKEW)) <= _CLOSE_WINDOW


def _companies_for_so(db, so_number: str) -> List[str]:
    """Every distinct company a core `sales_orders` row with this number exists in."""
    rows = (
        db.query(SalesOrder.company_id)
        .filter(SalesOrder.so_number == so_number)
        .distinct()
        .all()
    )
    return [str(r[0]) for r in rows]


def _company_code(db, company_id: str) -> Optional[str]:
    return db.query(Company.code).filter(Company.id == company_id).scalar()


def _match(db, entry, company_id: str) -> Optional[tuple]:
    """The one `(OrderInquiryRow, OrderInquiry)` an importer-closed ORDER row at this
    sheet row's identity, if there is one, in THIS company. `None` when nothing matches -
    unmatched, not created (AC-OB-16)."""
    q = (
        db.query(OrderInquiryRow, OrderInquiry)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .join(ProjectSalesOrder, ProjectSalesOrder.id == OrderInquiry.project_sales_order_id)
        .join(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
        # OUTER, so a row whose mirror names no core line (or whose core line carries no
        # date/warehouse of its own) still reaches the blank-cell fallback below rather
        # than being dropped from the join entirely.
        .outerjoin(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
        .outerjoin(
            SalesOrderLine, SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id
        )
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(SalesOrder.so_number == entry.so_number)
        .filter(SalesOrder.company_id == company_id)
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
        # Blank location cell today - match the row as the importer itself would have
        # left it: no location at all, or the core line's own warehouse code
        # (`raise_row`, ~:2772: `stock_location=location or match.line_location`).
        # `func.upper()` on the WAREHOUSE side: `raise_row` always writes
        # `OrderInquiryRow.stock_location` upper-cased (`location.strip().upper()`, and
        # the reader itself upper-cases a non-blank sheet cell the same way), but
        # `warehouses.warehouse_code` carries no such guarantee, so the comparison
        # normalises the side that might not already be upper rather than assuming both
        # are.
        q = q.filter(
            or_(
                OrderInquiryRow.stock_location.is_(None),
                OrderInquiryRow.stock_location == func.upper(Warehouse.warehouse_code),
            )
        )
    if entry.delivery_date is not None:
        q = q.filter(OrderInquiryRow.delivery_date == entry.delivery_date)
    else:
        # Same fallback for the date cell (`raise_row`, ~:2771:
        # `delivery_date=row.delivery_date or match.core_line.required_date`).
        q = q.filter(
            or_(
                OrderInquiryRow.delivery_date.is_(None),
                OrderInquiryRow.delivery_date == SalesOrderLine.required_date,
            )
        )
    return q.order_by(OrderInquiryRow.id.asc()).first()


def run(
    db, xlsx_paths: Sequence[str], apply: bool, company_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One dict per sheet row that reads ORDER BACK, across every book given (deduped by
    matching identity - see DEDUPE). Never raises on a bad file - a row from a file that
    could not be read is simply absent, the same as the upload path's own `problems` list.
    Raises `AmbiguousCompanyError` - before touching the database at all - when `apply` is
    set, no `company_code` is given, and some sheet row's SO number resolves to more than
    one company (see COMPANY SCOPE). Raises `ValueError` when `company_code` is given but
    names no company."""
    company_id: Optional[str] = None
    if company_code is not None:
        company_id = db.query(Company.id).filter(Company.code == company_code).scalar()
        if company_id is None:
            raise ValueError(f"no company with code {company_code}")
        company_id = str(company_id)

    entries = []
    for path in xlsx_paths:
        with open(path, "rb") as fh:
            data = fh.read()
        parsed = read_order_inquiry(data)
        entries.extend(entry for entry in parsed.rows if entry.order_back)

    # Every SO number this run will touch, and which companies its CORE sales order
    # exists in - resolved once per number, not once per entry.
    companies_by_so: Dict[str, List[str]] = {}
    for entry in entries:
        if entry.so_number not in companies_by_so:
            companies_by_so[entry.so_number] = _companies_for_so(db, entry.so_number)

    ambiguous = {
        so for so, ids in companies_by_so.items()
        if company_id is None and len(ids) > 1
    }
    if apply and ambiguous:
        raise AmbiguousCompanyError(ambiguous)

    # Every company this run will ever report against, resolved to its code ONCE rather
    # than once per entry (point 5/N3) - the explicit `--company`, plus every company any
    # SO number in the file resolves to.
    all_company_ids = {company_id} if company_id is not None else {
        cid for ids in companies_by_so.values() for cid in ids
    }
    company_codes = {cid: _company_code(db, cid) for cid in all_company_ids}

    results: List[Dict[str, Any]] = []
    # Keyed on the row's own MATCHING IDENTITY, not on a fresh `_match()` re-query: once
    # `--apply` has flushed a flip, a second identical sheet row's query would see the
    # row's now-`ORDER_BACK` verb and answer `unmatched` - a true statement about the SQL,
    # a misleading one about what happened (see DEDUPE). `(row_id, action)` from the FIRST
    # occurrence, so a repeat can relabel without touching the database again.
    seen: Dict[tuple, tuple] = {}
    for entry in entries:
        target_ids = [company_id] if company_id is not None else companies_by_so[entry.so_number]
        common = {
            "so_number": entry.so_number,
            "item_code": entry.item_code,
            "qty": entry.qty,
            "stock_location": entry.location,
            "remark": entry.remark,
        }
        if not target_ids:
            results.append({**common, "company_code": None, "action": "unmatched"})
            continue
        for company in target_ids:
            row_common = {**common, "company_code": company_codes.get(company)}
            identity = (
                company, entry.so_number, entry.item_code, _dec(entry.qty),
                entry.delivery_date, entry.location,
            )
            if identity in seen:
                _row_id, prior_action = seen[identity]
                if not apply:
                    # Dry run: reported ONCE (see DEDUPE).
                    continue
                action = "already_flipped" if prior_action == "flipped" else prior_action
                results.append({**row_common, "action": action})
                continue

            match = _match(db, entry, company)
            if match is None:
                results.append({**row_common, "action": "unmatched"})
                continue
            row, inquiry = match
            if (
                _is_importer_closed(row.actioned_at, inquiry.raised_at)
                and row.actioned_by == inquiry.raised_by
            ):
                action = "flipped"
                if apply:
                    row.verb = IV_ORDER_BACK
                    row.state = INQUIRY_RAISED
                    row.actioned_by = None
                    row.actioned_at = None
                    inquiry.state = INQUIRY_RAISED
                    # Flushed so a LATER query in this same run (another sheet row, or
                    # another company's own match) reads this row's post-flip state
                    # rather than a stale pre-flip one.
                    db.flush()
            else:
                action = "skipped_person_actioned"
            seen[identity] = (row.id, action)
            results.append({**row_common, "action": action})
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
    parser.add_argument(
        "--company", dest="company_code", default=None,
        help="narrow the match to one company code (e.g. SRT); required for --apply when "
             "a sheet's SO number exists in more than one company",
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
        # The match walks so_number -> projects.sales_orders -> order_inquiries itself,
        # scoped explicitly to one company by `--company` when given.
        set_company_scope(db, None)

        print(
            "Order Inquiry rows read as ORDER BACK "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'})"
            f"{f' in company {args.company_code}' if args.company_code else ''}:"
        )
        try:
            results = run(db, args.xlsx, apply, company_code=args.company_code)
        except AmbiguousCompanyError as exc:
            print(f"\nREFUSING to apply: {exc}")
            db.rollback()
            return 2
        except ValueError as exc:
            print(f"\nREFUSING: {exc}")
            db.rollback()
            return 2

        counts: Dict[str, int] = {}
        for entry in results:
            counts[entry["action"]] = counts.get(entry["action"], 0) + 1
            print(
                f"  [{entry['action']}] {entry['company_code'] or '?'} "
                f"SO {entry['so_number']} / {entry['item_code']} "
                f"qty {entry['qty']} @ {entry['stock_location'] or '(no location)'} "
                f"- remark {entry['remark']!r}"
            )

        print("\n=== summary ===")
        print(f"mode:                    {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"rows read as ORDER BACK: {len(results)}")
        print(f"flipped:                 {counts.get('flipped', 0)}")
        print(f"already flipped (dupe):  {counts.get('already_flipped', 0)}")
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
