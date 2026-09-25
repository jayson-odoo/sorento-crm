#!/usr/bin/env python3
"""Repair order inquiry rows stuck On PO/SPO with no document behind them.

Issue #1215 point 1 (diagnosis, 24 Sep 2026). `refresh_link_state`
(`ProjectOrderInquiryService`) is the ONE writer of a row's `state` / `po_ref` /
`po_line_id` / `spo_ref` - it derives all four from the row's own
`projects.order_inquiry_links` and its `bundled_qty` every time it runs. Every deleter of
a link inside the service (`_remove_links`, `_unplace_drafts`, `spo_conversion_service`,
`planning_change_service`, ...) calls it afterwards, so the four cannot normally drift.
23 Sep 2026's prod copy held 17 rows that had: nothing did. Their links were gone, their
`bundled_qty` was 0, and `state` still read `placed`/`partly_linked` with `po_ref`/
`spo_ref` still naming a document - so the worklist showed On PO/SPO and
`_assert_linkable`/the cascade's own query treated them as already covered, and nothing
ever looked at them again.

This is the REPAIR half. The GUARD half is in `ProjectOrderInquiryService.
auto_place_for_products`, which now re-derives every row it loads through
`refresh_link_state` before walking candidates - so a FUTURE silent delete like this one
heals itself the next time Auto link all, Link now or a purchase-order confirm runs, even
when the walk finds nothing to link in its place. This script is for the rows already
stuck before that guard existed.

Company wide, dry run by default. `--apply` is the only thing that writes:

    python scripts/repair_oi_stale_link_state.py            # dry run
    python scripts/repair_oi_stale_link_state.py --apply    # write

Idempotent: a second run finds nothing (a row `refresh_link_state` has already put back
to `raised` no longer matches the `placed`/`partly_linked` filter this script looks for).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.project_so import (  # noqa: E402
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService  # noqa: E402

#: The two states `refresh_link_state`'s own coverage formula can write for a row that
#: holds SOME cover - the states the diagnosis found stuck with none.
_STALE_STATES = (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED)

_NOTE_TAIL_WIDTH = 80


def find_stale_rows(db) -> list:
    """Every `placed`/`partly_linked` row with zero links AND zero bundle, company wide.

    NOT EXISTS rather than a NOT IN list of every linked row id: this runs against the
    real table with no company filter, and a correlated EXISTS is what the diagnosis's
    own disconfirming-check query used, so a person re-running that check by hand and
    this script agree on what "zero links" means.
    """
    has_link = (
        db.query(OrderInquiryLink.id)
        .filter(OrderInquiryLink.row_id == OrderInquiryRow.id)
        .exists()
    )
    return (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.state.in_(_STALE_STATES),
            OrderInquiryRow.bundled_qty == 0,
            ~has_link,
        )
        .order_by(OrderInquiryRow.id)
        .all()
    )


def _note_tail(note) -> str:
    if not note:
        return "(no note)"
    tail = note[-_NOTE_TAIL_WIDTH:]
    return f"...{tail}" if len(note) > _NOTE_TAIL_WIDTH else tail


def _counts(rows) -> dict:
    return {state: sum(1 for row in rows if row.state == state) for state in _STALE_STATES}


def _print_counts(label: str, rows) -> None:
    counts = _counts(rows)
    print(
        f"{label}: {len(rows)} rows "
        f"(placed {counts[INQUIRY_PLACED]}, partly_linked {counts[INQUIRY_PARTLY_LINKED]})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write the repair. Default is dry-run."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = find_stale_rows(db)
        _print_counts("before", rows)
        for row in rows:
            print(
                f"  {row.id} state={row.state} po_ref={row.po_ref!r} "
                f"spo_ref={row.spo_ref!r} note={_note_tail(row.note)!r}"
            )
        if not rows:
            print("nothing to repair")
            return 0
        if not args.apply:
            print("\nDry run only - nothing written. Re-run with --apply to write.")
            return 0

        ProjectOrderInquiryService(db).refresh_link_state(rows)
        db.flush()
        _print_counts("after", rows)
        db.commit()
        print("\nCommitted.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
