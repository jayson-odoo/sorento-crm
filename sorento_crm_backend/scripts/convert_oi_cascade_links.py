#!/usr/bin/env python3
"""Convert the existing "auto" order inquiry links on prod to the new rule.

`PLAN-oi-links-autocount-truth-24sep.md` section 3.8 (G5, issue #1215): before this
lane, every link the cascade walk wrote was a REAL link, `auto = true`, exactly like a
link the book (AutoCount) named. After S3/S4 the cascade only SUGGESTS - the walk's own
terminal write is now `projects.order_inquiry_suggested_links`, never a real link. This
script is the one-time conversion of what the OLD cascade already wrote on prod, so the
existing data matches the new rule the moment the deploy lands.

A SCRIPT, not a migration: classification needs the ORM helper
`ProjectOrderInquiryService._book_names_target_for_line` (a live join against sales
order / purchase order / SPO tables), which a migration cannot reach, and the owner
decides whether to apply only after seeing the dry run's counts (G5).

CLASSIFICATION (plan 3.8). Every link on a row in `raised` / `partly_linked` / `placed`
(`INQUIRY_LINK_STATES`) falls in exactly one class - `actioned` and `cancelled` rows are
never touched, because the row query never selects them:

    (a) book              auto and the book itself (`_book_names_target_for_line`,
                           never the row note's `auto:` stamp - AC-LT-44) names this
                           target for the row's own core line               -> nothing
    (b) cascade, open     auto, not book, target still open                -> becomes a
                                                                                suggested
                                                                                link (same
                                                                                target,
                                                                                qty,
                                                                                trigger
                                                                                "converted");
                                                                                the real
                                                                                link and
                                                                                its claim
                                                                                are removed
    (c) cascade, closed   auto, not book, target closed / received /       -> removed
                           retired                                            with its
                                                                                claim and a
                                                                                row note
    (d) not auto          manual, borrow, reallocation, shift, container   -> nothing
                           tick, moved received (`auto = false`)
    (e) CS reserve        `reserve_request_row_id` set                     -> nothing

Every row this script touches (one holding at least one class (b) or (c) link) is run
through `refresh_link_state` once, the same one writer of `state` / `po_ref` /
`po_line_id` / `spo_ref` every other caller uses - never a raw state write.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the default (no flags = dry run). `--apply` is the only thing that
writes. A second `--apply` finds nothing: a class (b)/(c) link no longer exists as a
real link once the first pass has converted or removed it, so the row's link set no
longer matches those classes.

COMPANY WIDE, ON PURPOSE
-------------------------
`SessionLocal()` on its own carries the fail-closed `UNSET` company scope (see
`app/database.py`'s `get_db`) - every owned-table query would return zero rows. This is
an operator script with no request and no principal, so it calls
`set_company_scope(db, None)`, the sanctioned system / all-companies scope
(`fold_oi_date_notices.py` does the same), and classifies and converts every company's
links in one pass, per company, in keyset pages (`OrderInquiryRow.id`, ordered,
`page_size` at a time) so a page never holds an unbounded scan of prod's row count.

Run from `sorento_crm_backend/`:
    venv/bin/python scripts/convert_oi_cascade_links.py            # dry run
    venv/bin/python scripts/convert_oi_cascade_links.py --apply    # write

Runs on the prod copy restored locally FIRST (never the cloud, never this session).
The counts go into the plan's section 7 for the owner to read before any `--apply` runs
against prod, which the owner does separately via `docker cp` + `docker exec`, as
`fold_oi_date_notices.py` did.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.procurement import InboundShipment, PurchaseOrderLine, SPOAllocation  # noqa: E402
from app.models.project_so import (  # noqa: E402
    INQUIRY_LINK_STATES,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import (  # noqa: E402
    ProjectOrderInquiryService,
    _dec,
    _qty_str,
    _ZERO,
)
from app.services.scm import spo_supply  # noqa: E402

#: One page of rows per company per query, so a company-wide scan never loads prod's
#: whole row count into memory at once.
PAGE_SIZE = 500

CLASS_BOOK = "a_book"
CLASS_CASCADE_OPEN = "b_cascade_open"
CLASS_CASCADE_CLOSED = "c_cascade_closed"
CLASS_NOT_AUTO = "d_not_auto"
CLASS_RESERVE = "e_reserve"

#: Print order and label, plan 3.8's own table.
_CLASS_LABELS = {
    CLASS_BOOK: "(a) book",
    CLASS_CASCADE_OPEN: "(b) cascade, open target",
    CLASS_CASCADE_CLOSED: "(c) cascade, closed/received/retired target",
    CLASS_NOT_AUTO: "(d) not auto",
    CLASS_RESERVE: "(e) CS reserve",
}
_CLASS_ORDER = [
    CLASS_BOOK, CLASS_CASCADE_OPEN, CLASS_CASCADE_CLOSED, CLASS_NOT_AUTO, CLASS_RESERVE,
]

#: AC-LT-42's own wording, verbatim - the class (c) row note, never the plain "Unlinked
#: from X" `_remove_links` writes for every other unlink in the app.
_CLOSED_TARGET_NOTE = (
    "Link to {document} removed: suggested by the cascade, not named by AutoCount "
    "(24 Sep ruling)"
)


def _target_open(db, link: OrderInquiryLink) -> bool:
    """Is `link`'s own PO line or SPO allocation still open - the same "closed,
    received or retired" test `links_for_rows`/`_received_documents_for` already state
    for a real link's own document (plan 3.8's (b) vs (c) split). A target row that no
    longer exists (the rare `ON DELETE SET NULL` case) is never open.
    """
    if link.po_line_id:
        found = (
            db.query(
                PurchaseOrderLine.line_status,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
            )
            .filter(PurchaseOrderLine.id == link.po_line_id)
            .first()
        )
        if found is None:
            return False
        line_status, qty_ordered, qty_received = found
        closed_or_received = line_status == "closed" or (
            _dec(qty_ordered) > _ZERO and _dec(qty_received) >= _dec(qty_ordered)
        )
        return not closed_or_received
    if link.spo_allocation_id:
        found = (
            db.query(
                SPOAllocation.line_status,
                SPOAllocation.receipt_status,
                SPOAllocation.retired_at,
                InboundShipment.actual_arrival_date,
            )
            .outerjoin(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .filter(SPOAllocation.id == link.spo_allocation_id)
            .first()
        )
        if found is None:
            return False
        line_status, receipt_status, retired_at, arrival_date = found
        if retired_at is not None:
            return False
        closed_or_received = (
            line_status == "closed"
            or (
                receipt_status is not None
                and receipt_status in spo_supply.RECEIVED_RECEIPT_STATUSES
            )
            or arrival_date is not None
        )
        return not closed_or_received
    return False


def _is_book_named(
    svc: ProjectOrderInquiryService, row: OrderInquiryRow, link: OrderInquiryLink
) -> bool:
    """AC-LT-44: reads the book itself, never the row note's `auto:` stamp - the book
    step runs INSIDE every cascade pass too (plan 2.1), so a note reading `auto:
    worklist` does not tell a cascade guess from a book link."""
    core_line_id = svc._core_line_id_for_row(row)
    if not core_line_id:
        return False
    core_line = svc._core_line_by_id(core_line_id)
    if core_line is None:
        return False
    return svc._book_names_target_for_line(
        core_line, po_line_id=link.po_line_id, spo_allocation_id=link.spo_allocation_id
    )


def classify_link(
    db, svc: ProjectOrderInquiryService, row: OrderInquiryRow, link: OrderInquiryLink
) -> str:
    """One of the five classes in plan 3.8's table, in the order it states them."""
    if link.reserve_request_row_id is not None:
        return CLASS_RESERVE
    if not link.auto:
        return CLASS_NOT_AUTO
    if _is_book_named(svc, row, link):
        return CLASS_BOOK
    if _target_open(db, link):
        return CLASS_CASCADE_OPEN
    return CLASS_CASCADE_CLOSED


def _company_ids_with_linkable_rows(db) -> List[str]:
    return sorted(
        {
            str(company_id)
            for (company_id,) in db.query(OrderInquiryRow.company_id)
            .filter(OrderInquiryRow.state.in_(INQUIRY_LINK_STATES))
            .distinct()
        }
    )


#: The minimum possible UUID - a valid cast, and less than any real row id, so the
#: FIRST page's `id > last_id` test is exactly "everything" without a special case.
_MIN_UUID = "00000000-0000-0000-0000-000000000000"


def _row_pages(db, company_id: str, page_size: int = PAGE_SIZE):
    """Keyset pages of a company's linkable rows, ordered by id - never a single
    unbounded scan of prod's row count."""
    last_id = _MIN_UUID
    while True:
        page = (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.company_id == company_id,
                OrderInquiryRow.state.in_(INQUIRY_LINK_STATES),
                OrderInquiryRow.id > last_id,
            )
            .order_by(OrderInquiryRow.id)
            .limit(page_size)
            .all()
        )
        if not page:
            return
        yield page
        last_id = page[-1].id


def run(db, *, apply: bool = False) -> Dict[str, Any]:
    """Classify every link on every linkable row, company by company, and - only when
    `apply` - convert class (b), remove class (c), and refresh every touched row once.
    The caller commits.
    """
    svc = ProjectOrderInquiryService(db)
    class_counts: Dict[str, Counter] = {}
    transition_counts: Dict[str, Counter] = {}
    qty_delta: Dict[str, Decimal] = {}
    touched_rows: List[OrderInquiryRow] = []

    for company_id in _company_ids_with_linkable_rows(db):
        counts: Counter = Counter()
        transitions: Counter = Counter()
        delta = _ZERO
        for page in _row_pages(db, company_id):
            links_by_row = svc._links_by_row([row.id for row in page])
            for row in page:
                links = links_by_row.get(str(row.id), [])
                if not links:
                    continue
                takes: List[Tuple[Dict[str, Any], Decimal]] = []
                to_remove_b: List[OrderInquiryLink] = []
                to_remove_c: List[OrderInquiryLink] = []
                real_remaining = _ZERO
                for link in links:
                    link_class = classify_link(db, svc, row, link)
                    counts[link_class] += 1
                    qty = _dec(link.qty)
                    if link_class == CLASS_CASCADE_OPEN:
                        takes.append(
                            (
                                {
                                    "po_line_id": link.po_line_id,
                                    "spo_allocation_id": link.spo_allocation_id,
                                    "document": link.document,
                                },
                                qty,
                            )
                        )
                        to_remove_b.append(link)
                        delta += qty
                    elif link_class == CLASS_CASCADE_CLOSED:
                        to_remove_c.append(link)
                        delta += qty
                    else:
                        real_remaining += qty

                if not to_remove_b and not to_remove_c:
                    continue

                new_state = ProjectOrderInquiryService._coverage_state(
                    _dec(row.qty), real_remaining, _dec(row.bundled_qty)
                )
                if new_state != row.state:
                    transitions[(row.state, new_state)] += 1

                if apply:
                    removed_c_documents = [link.document for link in to_remove_c]
                    svc._remove_links(row, [*to_remove_b, *to_remove_c])
                    for document in removed_c_documents:
                        stamp = _CLOSED_TARGET_NOTE.format(document=document or "the document")
                        row.note = f"{row.note}; {stamp}" if row.note else stamp
                    if takes:
                        svc._write_suggested_links(row, takes, "converted")
                    touched_rows.append(row)

        class_counts[company_id] = counts
        transition_counts[company_id] = transitions
        qty_delta[company_id] = delta

    if apply and touched_rows:
        svc.refresh_link_state(touched_rows)
        db.flush()

    return {
        "class_counts": class_counts,
        "transition_counts": transition_counts,
        "qty_delta": qty_delta,
        "touched_row_count": len(touched_rows),
    }


def _print_summary(summary: Dict[str, Any], *, applied: bool) -> None:
    class_counts = summary["class_counts"]
    transition_counts = summary["transition_counts"]
    qty_delta = summary["qty_delta"]

    total_counts: Counter = Counter()
    total_transitions: Counter = Counter()
    total_delta = _ZERO

    print(f"mode: {'APPLIED' if applied else 'DRY-RUN (no writes)'}")

    print("\n=== counts per class, per company ===")
    for company_id in sorted(class_counts):
        counts = class_counts[company_id]
        print(f"  company {company_id}:")
        for link_class in _CLASS_ORDER:
            n = counts.get(link_class, 0)
            total_counts[link_class] += n
            print(f"    {_CLASS_LABELS[link_class]}: {n}")

    print("\n=== rows whose state would change, per company ===")
    for company_id in sorted(transition_counts):
        transitions = transition_counts[company_id]
        if not transitions:
            print(f"  company {company_id}: none")
            continue
        print(f"  company {company_id}:")
        for (old_state, new_state), n in sorted(transitions.items()):
            total_transitions[(old_state, new_state)] += n
            print(f"    {old_state} -> {new_state}: {n}")

    print("\n=== To buy quantity delta, per company ===")
    for company_id in sorted(qty_delta):
        delta = qty_delta[company_id]
        total_delta += delta
        print(f"  company {company_id}: {_qty_str(delta)}")

    print("\n=== totals ===")
    for link_class in _CLASS_ORDER:
        print(f"  {_CLASS_LABELS[link_class]}: {total_counts.get(link_class, 0)}")
    print(f"  rows whose state would change: {sum(total_transitions.values())}")
    print(
        "  of which placed -> raised: "
        f"{total_transitions.get((INQUIRY_PLACED, INQUIRY_RAISED), 0)}"
    )
    print(f"  To buy quantity delta: {_qty_str(total_delta)}")
    print(f"  rows touched: {summary['touched_row_count']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write the conversion. Default is dry-run."
    )
    args = parser.parse_args()

    db = SessionLocal()
    # Company wide on purpose (module docstring): a script has no request and no
    # principal, so the session scope would otherwise be the fail-closed UNSET.
    set_company_scope(db, None)
    try:
        summary = run(db, apply=args.apply)
        _print_summary(summary, applied=args.apply)
        if args.apply:
            db.commit()
            print("\nCommitted.")
        else:
            print("\nDry run only - nothing written. Re-run with --apply to write.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
