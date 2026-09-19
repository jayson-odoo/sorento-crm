#!/usr/bin/env python3
"""Run `follow_book_for_rows` once over every existing order inquiry row.

S4 (`PLAN-oi-follow-book-chain.md`, AC-FB-40 to AC-FB-42). S1-S3 wired the book
into the two ingest hooks and the ordinary cascade, so a row created or
re-cascaded from here on already follows AutoCount's book (D3: "the book
wins, always"). A row that has sat untouched since before those slices landed
never gets the chance - this script gives every existing row that one pass,
company by company, without waiting for its next natural cascade.

WHAT IT DOES
------------
Per company, pages `order_inquiry_rows` by id (never OFFSET - a page that
edits earlier rows would shift a later OFFSET page, see
`scripts/backfill_requested_by_contact.py`) and hands each page to
`ProjectOrderInquiryService.follow_book_for_rows` - the SAME rule the ingest
hooks and the cascade call, never a second one. `max_rows=None` (AC-FB-24's
cap is an ingest-surface guard, not a standing rule; see the fix-round note on
`follow_book_for_rows` itself) so a page is never silently short-changed.

SAFETY / IDEMPOTENCY
---------------------
`follow_book_for_rows` only ever links a row that still has need left and only
ever displaces a holder the book itself has moved on from (D3, AC-FB-33's
exemption), so a second run over rows this script already touched reports
zero - there is nothing left to do, not a guard bolted on top.

`--dry-run` is the DEFAULT and writes nothing: each page runs through the
real code path inside its own SAVEPOINT, counted, then rolled back, so a dry
run can never disagree with what `--apply` would actually do - it is the same
call, just not kept. `--apply` commits per page (never one all-company
transaction - a page that failed should not roll back pages already written).

Prints per company: rows the book names (same narrowing
`follow_book_for_rows` applies internally - `_linkable_rows_with_core_line`
then `_refs_named_by_book`), rows linked, quantity linked, rows displaced.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_oi_follow_book.py
    venv/bin/python scripts/backfill_oi_follow_book.py --apply
    venv/bin/python scripts/backfill_oi_follow_book.py --apply --batch 500
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.models.base import company_scope, set_company_scope
from app.models.company import Company
from app.models.project_so import OrderInquiryLink, OrderInquiryRow
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

_ZERO = Decimal("0")


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else _ZERO


def _all_company_ids(db) -> List[str]:
    """Every company that owns at least one order inquiry row, in a stable order."""
    with company_scope(db, None):
        rows = (
            db.query(OrderInquiryRow.company_id)
            .filter(OrderInquiryRow.company_id.isnot(None))
            .distinct()
            .all()
        )
    return sorted({str(company_id) for (company_id,) in rows})


def _company_label(db, company_id: str) -> str:
    row = db.query(Company.name, Company.code).filter(Company.id == company_id).first()
    if not row:
        return company_id
    name, code = row
    return f"{name} ({code})" if code else name


def _rows_named_by_book(db, service: ProjectOrderInquiryService, company_id: str) -> set:
    """Of every row in this company, the ones whose core line's ref the book
    states - the exact narrowing `follow_book_for_rows` applies to itself
    (`_linkable_rows_with_core_line` then `_refs_named_by_book`), so this
    count is "what a follow-book pass can ever touch", never a second rule."""
    all_ids = [
        str(row_id)
        for (row_id,) in db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.company_id == company_id)
        .all()
    ]
    named: set = set()
    page = 500
    for i in range(0, len(all_ids), page):
        chunk = all_ids[i : i + page]
        _rows_by_id, core_line_by_row = service._linkable_rows_with_core_line(chunk)
        if not core_line_by_row:
            continue
        candidate_refs = {
            (core_line.source_ref or "").strip()
            for core_line in core_line_by_row.values()
            if (core_line.source_ref or "").strip()
        }
        named_refs = service._refs_named_by_book(candidate_refs)
        for row_id, core_line in core_line_by_row.items():
            if (core_line.source_ref or "").strip() in named_refs:
                named.add(row_id)
    return named


def _company_link_snapshot(db, company_id: str) -> Dict[str, Dict[str, Decimal]]:
    """Every order_inquiry_row in this company that carries a link, per TARGET
    it is linked to - the one comparison a page's before and after read to
    find what THIS page actually changed, whichever row it landed on (a book
    row it linked, or a holder it displaced).

    Per-target, not a per-row total (review round item 10, reviewer finding
    10): a displaced holder the trailing cascade re-links to a DIFFERENT
    document for the SAME quantity leaves the row's own total unchanged, so a
    total-only comparison would see nothing happened to it at all - the
    book's own displacement would vanish from the report. Comparing the
    target set (and each one's qty) catches that: the OLD target dropping out
    is a displacement, the NEW one appearing is a link, on the same row, in
    the same page."""
    rows = (
        db.query(
            OrderInquiryLink.row_id,
            func.coalesce(OrderInquiryLink.po_line_id, OrderInquiryLink.spo_allocation_id),
            OrderInquiryLink.qty,
        )
        .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
        .filter(OrderInquiryRow.company_id == company_id)
        .all()
    )
    snapshot: Dict[str, Dict[str, Decimal]] = {}
    for row_id, target_id, qty in rows:
        snapshot.setdefault(str(row_id), {})[str(target_id)] = _dec(qty)
    return snapshot


def run_company(db, company_id: str, *, apply: bool, batch: int) -> Dict[str, Any]:
    """Page one company's rows through `follow_book_for_rows`. The caller
    has already entered this company's scope."""
    # Review round item 8: a fresh service instance per page, never one reused
    # across pages - `ProjectOrderInquiryService` memoises per-instance
    # (`_linked_by_target`, claims, awaiting-link tallies) for the length of
    # ONE cascade pass; carrying that memo across pages this script itself
    # commits between would answer a later page with an earlier page's totals.
    named_rows = _rows_named_by_book(db, ProjectOrderInquiryService(db), company_id)

    rows_linked: set = set()
    quantity_linked = _ZERO
    rows_displaced: set = set()

    last_id: Optional[str] = None
    while True:
        q = db.query(OrderInquiryRow.id).filter(OrderInquiryRow.company_id == company_id)
        if last_id is not None:
            q = q.filter(OrderInquiryRow.id > last_id)
        page_ids = [
            str(row_id)
            for (row_id,) in q.order_by(OrderInquiryRow.id.asc()).limit(batch).all()
        ]
        if not page_ids:
            break
        last_id = page_ids[-1]

        before = _company_link_snapshot(db, company_id)
        savepoint = None if apply else db.begin_nested()
        ProjectOrderInquiryService(db).follow_book_for_rows(
            page_ids, trigger="backfill", company_id=company_id, max_rows=None,
        )
        db.flush()
        after = _company_link_snapshot(db, company_id)

        for row_id in set(before) | set(after):
            before_targets = before.get(row_id, {})
            after_targets = after.get(row_id, {})
            for target_id, qty in after_targets.items():
                was = before_targets.get(target_id, _ZERO)
                if qty > was:
                    rows_linked.add(row_id)
                    quantity_linked += qty - was
            for target_id, qty in before_targets.items():
                now = after_targets.get(target_id, _ZERO)
                if now < qty:
                    rows_displaced.add(row_id)

        if apply:
            db.commit()
        else:
            savepoint.rollback()

    return {
        "rows_named_by_book": len(named_rows),
        "rows_linked": len(rows_linked),
        "quantity_linked": quantity_linked,
        "rows_displaced": len(rows_displaced),
    }


def run(db, *, apply: bool, batch: int, company_ids: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Every company, in order. Returns each company's summary keyed by id."""
    ids = list(company_ids) if company_ids is not None else _all_company_ids(db)
    summaries: Dict[str, Dict[str, Any]] = {}
    for company_id in ids:
        with company_scope(db, frozenset({company_id})):
            summary = run_company(db, company_id, apply=apply, batch=batch)
        summaries[company_id] = summary
        label = _company_label(db, company_id)
        print(f"\n{label}:")
        print(f"  rows named by the book: {summary['rows_named_by_book']}")
        print(f"  rows linked:            {summary['rows_linked']}")
        print(f"  quantity linked:        {summary['quantity_linked']}")
        print(f"  rows displaced:         {summary['rows_displaced']}")
    return summaries


def main(argv: Optional[Sequence[str]] = None, db=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="(default) report only, writes nothing - each page runs, is counted, then rolled back",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write the changes; commits after each page",
    )
    parser.add_argument("--batch", type=int, default=500, help="rows per page (default 500).")
    args = parser.parse_args(argv)
    apply = bool(args.apply)
    if apply:
        args.dry_run = False

    owns_db = db is None
    if db is None:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        # A script has no request and no principal, so the session scope would
        # be UNSET (fail-closed, 0 rows). Each company is scoped explicitly
        # below, the same way the ingest hooks pin `follow_book_for_rows`'s
        # own scope to one company at a time.
        set_company_scope(db, None)

        print(
            "Order inquiry rows following the AutoCount book "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summaries = run(db, apply=apply, batch=args.batch)

        totals = {
            "rows_named_by_book": sum(s["rows_named_by_book"] for s in summaries.values()),
            "rows_linked": sum(s["rows_linked"] for s in summaries.values()),
            "quantity_linked": sum((s["quantity_linked"] for s in summaries.values()), _ZERO),
            "rows_displaced": sum(s["rows_displaced"] for s in summaries.values()),
        }
        print("\n=== summary, all companies ===")
        print(f"mode:                   {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"companies:              {len(summaries)}")
        print(f"rows named by the book: {totals['rows_named_by_book']}")
        print(f"rows linked:            {totals['rows_linked']}")
        print(f"quantity linked:        {totals['quantity_linked']}")
        print(f"rows displaced:         {totals['rows_displaced']}")
        if not apply and totals["rows_linked"]:
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
