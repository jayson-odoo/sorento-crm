#!/usr/bin/env python3
"""Restate legacy order inquiry sheet rows that squat another sales order line.

OI-LEGACY-DUP-REPAIR (`documentation/plans/scm/PLAN-oi-legacy-dup-repair-30oct.md`).

WHY THIS EXISTS
----------------
The 20 Sep 2026 sheet uploads ran the five-pass line pick that predates
`_pick_lines_by_date_order`. Rule R5 counts identical rows on one tab as separate
instructions, so a tab that stated the same SO / item / qty / date twice raised two rows.
When the sales order had only ONE line for that delivery, the first row took it and the
second fell through to the fallback pass, which put it on the earliest open line with room:
a line with a different quantity and a different date (OI-2609-0676 / M9713SS: 2 due
2026-10-07 on the line of 26 due 2027-04-07). The next book's row for THAT line was then
skipped `already_raised`, so the line's own instruction was never raised and the duplicate
sits in its place, asking for 2 where the line needs 26.

WHAT IT FINDS (`find_squatters`, read-only)
--------------------------------------------
A row the sheet import CREATED, when all of these hold, read off `import_job_rows`:

* the same job created another row from a DIFFERENT sheet row with the identical identity
  (tab, SO, item, qty, delivery date), and that row sits on a line whose qty and date are
  the sheet's;
* this row's line has neither the sheet's qty nor the sheet's date;
* a sheet row from the same or a later upload names this line exactly (same SO and item,
  the line's date AND the line's qty) and was skipped `already_raised`.

WHAT IT WRITES (`--apply`)
---------------------------
Only a `raised` row with no links, no reserve request rows and no bundle, still carrying
the sheet's qty and date, and the only live row on its line. Its qty and date become the skipped row's (which are the line's):
exactly the row that skipped instruction would have raised. `previous_qty` /
`previous_delivery_date` keep the Was, the note names both sheet rows, an acknowledged row
goes back to `changed` so purchasing re-reads it, and each row gets one audit EVENT. Every
other match is printed with the reason it is held, never written.

SAFETY / IDEMPOTENCY
---------------------
Dry run is the default. `--apply` needs `--expect N`, the restate count the dry run
printed, and refuses (writing nothing) when the count found at apply time differs. A
restated row reads "already restated" on the next run, so a second `--apply` writes
nothing. `run()` does not commit; `main()` does, after `run()` returns.

Run from sorento_crm_backend/:
    venv/bin/python scripts/repair_oi_legacy_dup_rows.py
    venv/bin/python scripts/repair_oi_legacy_dup_rows.py --inquiry-no OI-2609-0676
    venv/bin/python scripts/repair_oi_legacy_dup_rows.py --apply --expect 12
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import Date, Numeric, cast, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.job import ImportJob, ImportJobRow  # noqa: E402
from app.models.project_so import (  # noqa: E402
    ACK_ACKNOWLEDGED,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.services.audit_service import log_audit  # noqa: E402
from app.services.project_order_inquiry_service import ProjectOrderInquiryService  # noqa: E402

_JOB_TYPE = "order_inquiry_import"
_EVENT = "OI_ROW_LEGACY_DUP_RESTATED"
RESTATE = "restate"


class CountMismatch(RuntimeError):
    """`--apply` found a different number of rows to restate than `--expect` names."""


@dataclass
class Squatter:
    row_id: str
    inquiry_no: Optional[str]
    item_code: Optional[str]
    state: str
    qty: Decimal
    delivery_date: Optional[date]
    line_no: int
    sheet: str
    sheet_row: Optional[int]
    sibling_row_id: str
    sibling_sheet_row: Optional[int]
    skipped_sheet: str
    skipped_sheet_row: Optional[int]
    sheet_qty: Decimal
    sheet_date: date
    restate_qty: Decimal
    restate_date: date
    verdict: str


def _text(job_row, key: str):
    return job_row.identity[key].astext


def _qty(job_row):
    return cast(func.nullif(_text(job_row, "qty"), ""), Numeric(15, 4))


def _date(job_row):
    return cast(func.nullif(_text(job_row, "delivery_date"), ""), Date)


def _imported(db: Session, code: str, *extra):
    """Sheet-import job rows with `code`, read through their identity. One scan."""
    j = ImportJobRow
    return (
        db.query(
            j.entity_id, j.row_number, ImportJob.created_at,
            _text(j, "sheet"), _text(j, "doc_no"), _text(j, "item_code"), _qty(j), _date(j),
        )
        .join(ImportJob, ImportJob.id == j.import_job_id)
        .filter(ImportJob.job_type == _JOB_TYPE, j.code == code, _date(j).isnot(None), *extra)
    )


def _twin_groups(db: Session) -> List[list]:
    """Created rows whose job + tab + SO + item + qty + date occurs on more than one sheet row.

    A window count over one scan of the created job rows, rather than a self-join of a
    100k-row table on JSONB expressions (measured: the self-join ran past ten minutes on
    the 28 Oct prod copy).
    """
    j = ImportJobRow
    key = (j.import_job_id, _text(j, "sheet"), _text(j, "doc_no"), _text(j, "item_code"), _qty(j), _date(j))
    inner = (
        _imported(db, "created", j.entity_type == "order_inquiry_row")
        .add_columns(j.import_job_id, func.count().over(partition_by=key).label("n"))
        .subquery()
    )
    groups: dict = {}
    for entity_id, sheet_row, job_at, sheet, doc_no, item, qty, due, job_id, n in (
        db.query(inner).filter(inner.c.n > 1).all()
    ):
        groups.setdefault((job_id, sheet, doc_no, item, qty, due), []).append(
            (entity_id, sheet_row, job_at, sheet, doc_no, item, qty, due)
        )
    return [sorted(members, key=lambda m: (m[1] is None, m[1])) for members in groups.values()]


def _rows_on_lines(db: Session, row_ids, inquiry_id: Optional[str]) -> dict:
    """{row id: (row, inquiry_no, line)} for the rows the job rows created, if they exist."""
    out: dict = {}
    ids = sorted(row_ids)
    for i in range(0, len(ids), 1000):
        query = (
            db.query(OrderInquiryRow, OrderInquiry.inquiry_no, ProjectSalesOrderLine)
            .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
            .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
            .filter(OrderInquiryRow.id.in_(ids[i:i + 1000]))
        )
        if inquiry_id is not None:
            query = query.filter(OrderInquiryRow.order_inquiry_id == inquiry_id)
        for row, inquiry_no, line in query.all():
            out[str(row.id)] = (row, inquiry_no, line)
    return out


def _verdict(db: Session, row: OrderInquiryRow, sheet_qty, sheet_date, restate_qty, restate_date) -> str:
    if row.state == INQUIRY_CANCELLED:
        return "cancelled"
    # Restating adds the line's FULL qty; with another live row on the line (a second copy,
    # or a real instruction) that would ask for the line twice (review of PR #1996).
    if (
        db.query(OrderInquiryRow.id)
        .filter(
            OrderInquiryRow.so_line_id == row.so_line_id,
            OrderInquiryRow.id != row.id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .first()
    ):
        return "line carries other rows"
    if row.qty == restate_qty and row.delivery_date == restate_date:
        return "already restated"
    if db.query(OrderInquiryLink.id).filter(OrderInquiryLink.row_id == row.id).first():
        return "linked"
    if (
        db.query(OrderInquiryReserveRequestRow.id)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .first()
    ):
        return "reserve request"
    if (row.bundled_qty or 0) > 0 or (
        db.query(OrderInquiryRow.id).filter(OrderInquiryRow.bundled_with_row_id == row.id).first()
    ):
        return "bundled"
    if row.state != INQUIRY_RAISED:
        return row.state
    if row.qty != sheet_qty or row.delivery_date != sheet_date:
        return "edited since import"
    return RESTATE


def find_squatters(db: Session, *, inquiry_id: Optional[str] = None) -> List[Squatter]:
    """Every squatter (see the module docstring), with its evidence and verdict. Read-only."""
    groups = _twin_groups(db)
    placed = _rows_on_lines(db, {m[0] for members in groups for m in members}, inquiry_id)

    pending = []  # (member, row, inquiry_no, line, twin member, twin row)
    for members in groups:
        on_sheet_line = [
            (m, placed[m[0]][0]) for m in members
            if m[0] in placed
            and (placed[m[0]][2].qty, placed[m[0]][2].delivery_date) == (m[6], m[7])
        ]
        for m in members:
            if m[0] not in placed:
                continue
            row, inquiry_no, line = placed[m[0]]
            # neither the sheet's qty nor its date: a line this sheet row was never for
            if line.qty == m[6] or line.delivery_date == m[7]:
                continue
            twin = next(
                (
                    (t, trow) for t, trow in on_sheet_line
                    if t[1] != m[1] and trow.so_line_id != row.so_line_id
                ),
                None,
            )
            if twin is not None:
                pending.append((m, row, inquiry_no, line, twin[0], twin[1]))
    if not pending:
        return []

    # the blocked instruction: a sheet row from the same or a later upload, naming the
    # duplicate's line exactly, skipped because a row already sat there
    docs = sorted({m[4] for m, *_ in pending})
    skipped = sorted(
        _imported(db, "already_raised", _text(ImportJobRow, "doc_no").in_(docs)).all(),
        key=lambda b: (b[2], b[1] is None, b[1]),
    )
    found: List[Squatter] = []
    seen = set()
    for m, row, inquiry_no, line, twin, twin_row in pending:
        if row.id in seen:
            continue
        hit = next(
            (
                b for b in skipped
                if (b[4], b[5], b[6], b[7]) == (m[4], m[5], line.qty, line.delivery_date)
                and b[2] >= m[2]
            ),
            None,
        )
        if hit is None:
            continue
        seen.add(row.id)
        found.append(
            Squatter(
                row_id=str(row.id), inquiry_no=inquiry_no, item_code=row.item_code,
                state=row.state, qty=row.qty, delivery_date=row.delivery_date,
                line_no=line.line_no, sheet=m[3], sheet_row=m[1],
                sibling_row_id=str(twin_row.id), sibling_sheet_row=twin[1],
                skipped_sheet=hit[3], skipped_sheet_row=hit[1], sheet_qty=m[6],
                sheet_date=m[7], restate_qty=line.qty, restate_date=line.delivery_date,
                verdict=_verdict(db, row, m[6], m[7], line.qty, line.delivery_date),
            )
        )
    return sorted(found, key=lambda f: (f.inquiry_no or "", f.item_code or "", f.line_no))


def _num(value: Decimal):
    return int(value) if value == value.to_integral_value() else float(value)


def _restate(db: Session, hit: Squatter, now: datetime) -> None:
    row = db.get(OrderInquiryRow, hit.row_id)
    old = {"qty": _num(row.qty), "delivery_date": row.delivery_date.isoformat()}
    row.previous_qty = row.qty
    row.previous_delivery_date = row.delivery_date
    row.qty = hit.restate_qty
    row.delivery_date = hit.restate_date
    # Mirrors settle-in-place: purchasing re-reads a row it had already taken on; a row
    # still awaiting says nothing, nobody read it yet.
    if row.ack_state in (ACK_ACKNOWLEDGED, ACK_CHANGED):
        row.ack_state = ACK_CHANGED
        row.changed_at = now
    row.note = "; ".join(filter(None, [row.note, (
        f"Restated {now.date().isoformat()}: was {old['qty']} on "
        f"{old['delivery_date']}, a second copy of {hit.sheet} row {hit.sibling_sheet_row} "
        f"put on this line; now this line's own {hit.skipped_sheet} row {hit.skipped_sheet_row}"
    )]))
    log_audit(
        db,
        "project_order_inquiry_rows",
        str(row.id),
        "EVENT",
        event=_EVENT,
        old_values=old,
        new_values={
            "qty": _num(row.qty),
            "delivery_date": row.delivery_date.isoformat(),
            "sheet_row": f"{hit.sheet} row {hit.sheet_row}",
            "twin_sheet_row": f"{hit.sheet} row {hit.sibling_sheet_row}",
            "skipped_sheet_row": f"{hit.skipped_sheet} row {hit.skipped_sheet_row}",
        },
        company_id=row.company_id,
        reason="OI-LEGACY-DUP-REPAIR",
        skip_flush=True,
    )


def run(
    db: Session,
    *,
    apply: bool,
    expect: Optional[int],
    inquiry_id: Optional[str] = None,
) -> dict:
    """Find, print, and (with `apply`) restate. Never commits."""
    found = find_squatters(db, inquiry_id=inquiry_id)
    to_restate = [hit for hit in found if hit.verdict == RESTATE]
    for hit in found:
        print(
            f"  {hit.inquiry_no} {hit.item_code} line {hit.line_no}: "
            f"{_num(hit.qty)} on {hit.delivery_date} ({hit.state}) "
            f"from {hit.sheet} row {hit.sheet_row} (twin row {hit.sibling_sheet_row}); "
            f"skipped {hit.skipped_sheet} row {hit.skipped_sheet_row} = "
            f"{_num(hit.restate_qty)} on {hit.restate_date} -> {hit.verdict} [{hit.row_id}]"
        )
    held = len(found) - len(to_restate)
    print(f"found {len(found)}: restate {len(to_restate)}, held {held}")
    result = {"found": len(found), "restate": len(to_restate), "held": held, "restated": 0}
    if not apply:
        return result
    if expect is None or expect != len(to_restate):
        raise CountMismatch(
            f"--expect {expect} but {len(to_restate)} rows would be restated now; "
            "re-run the dry run and pass the count it prints"
        )
    now = datetime.utcnow()
    for hit in to_restate:
        _restate(db, hit, now)
    db.flush()
    # The one writer of state and bundles re-derives them, as settle-in-place does
    # (`project_order_inquiry_service.py:3001`): a companion sized off this row's old qty
    # follows the new one. An unlinked raised row stays raised.
    ProjectOrderInquiryService(db).refresh_link_state(
        [db.get(OrderInquiryRow, hit.row_id) for hit in to_restate]
    )
    db.flush()
    result["restated"] = len(to_restate)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    parser.add_argument("--expect", type=int, help="With --apply: the dry run's restate count.")
    parser.add_argument("--inquiry-no", help="Restrict to one inquiry, e.g. OI-2609-0676.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        inquiry_id = None
        if args.inquiry_no:
            inquiry = db.query(OrderInquiry).filter(OrderInquiry.inquiry_no == args.inquiry_no).one_or_none()
            if inquiry is None:
                print(f"no inquiry {args.inquiry_no}")
                return 1
            inquiry_id = inquiry.id
        try:
            result = run(db, apply=args.apply, expect=args.expect, inquiry_id=inquiry_id)
        except CountMismatch as exc:
            db.rollback()
            print(f"REFUSED: {exc}")
            return 2
        if not args.apply:
            print("\nDry run only - nothing written. Re-run with --apply --expect "
                  f"{result['restate']} to write.")
            return 0
        db.commit()
        print(f"\nCommitted: {result['restated']} rows restated.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
