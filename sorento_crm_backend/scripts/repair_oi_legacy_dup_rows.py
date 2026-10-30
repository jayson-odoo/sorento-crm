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
* a sheet row read at or after this one names this line exactly (same SO and item, the
  line's date AND the line's qty) and was skipped `already_raised`.

WHAT IT WRITES (`--apply`)
---------------------------
Only a `raised` row with no links, no reserve request rows and no bundle, still carrying
the sheet's qty and date. Its qty and date become the skipped row's (which are the line's):
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

from sqlalchemy import Date, Numeric, String, cast, func  # noqa: E402
from sqlalchemy.orm import Session, aliased  # noqa: E402

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


def _candidates(db: Session, inquiry_id: Optional[str]):
    """One result row per (squatter, twin, skipped row), squatter first; twins unchecked.

    ORM constructs rather than raw SQL so a test's scratch schema translates the
    `projects.` tables too (`tests/_pg_fixture.py`, `blank_session`). The two
    company-scoped classes appear ONCE each, unaliased: the scope listener adapts to one
    occurrence of a class per statement (`app/api/v1/scm/order_inquiry_conflicts.py`), so
    the twin's own row and line are read by `_twins_on_their_lines` instead.
    """
    cj, sj, bj = aliased(ImportJobRow), aliased(ImportJobRow), aliased(ImportJobRow)
    cjob, bjob = aliased(ImportJob), aliased(ImportJob)
    line = ProjectSalesOrderLine

    query = (
        db.query(
            OrderInquiryRow, OrderInquiry.inquiry_no, line.line_no, line.qty, line.delivery_date,
            _text(cj, "sheet"), cj.row_number, _qty(cj), _date(cj),
            sj.entity_id, sj.row_number, _text(bj, "sheet"), bj.row_number,
        )
        .select_from(cj)
        .join(cjob, cjob.id == cj.import_job_id)
        .join(OrderInquiryRow, cj.entity_id == cast(OrderInquiryRow.id, String))
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .join(line, line.id == OrderInquiryRow.so_line_id)
        # the twin: same job, same tab, same identity, a different sheet row
        .join(
            sj,
            (sj.import_job_id == cj.import_job_id)
            & (sj.id != cj.id)
            & (sj.code == "created")
            & (sj.entity_type == "order_inquiry_row")
            & (_text(sj, "sheet") == _text(cj, "sheet"))
            & (_text(sj, "doc_no") == _text(cj, "doc_no"))
            & (_text(sj, "item_code") == _text(cj, "item_code"))
            & (_qty(sj) == _qty(cj))
            & (_date(sj) == _date(cj)),
        )
        # the blocked instruction: a sheet row read at or after this one, naming this
        # row's line exactly, skipped because this row already sat there
        .join(
            bj,
            (bj.code == "already_raised")
            & (_text(bj, "doc_no") == _text(cj, "doc_no"))
            & (_text(bj, "item_code") == _text(cj, "item_code"))
            & (_date(bj) == line.delivery_date)
            & (_qty(bj) == line.qty),
        )
        .join(bjob, bjob.id == bj.import_job_id)
        .filter(
            cjob.job_type == _JOB_TYPE,
            bjob.job_type == _JOB_TYPE,
            bjob.created_at >= cjob.created_at,
            cj.code == "created",
            cj.entity_type == "order_inquiry_row",
            line.qty != _qty(cj),
            line.delivery_date != _date(cj),
        )
        .order_by(OrderInquiryRow.id, sj.row_number, bjob.created_at, bj.row_number)
    )
    if inquiry_id is not None:
        query = query.filter(OrderInquiryRow.order_inquiry_id == inquiry_id)
    return query.all()


def _twins_on_their_lines(db: Session, twin_ids) -> dict:
    """{twin row id: (so_line_id, line qty, line date)} for the twins `_candidates` named."""
    if not twin_ids:
        return {}
    rows = (
        db.query(
            OrderInquiryRow.id, OrderInquiryRow.so_line_id,
            ProjectSalesOrderLine.qty, ProjectSalesOrderLine.delivery_date,
        )
        .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
        .filter(OrderInquiryRow.id.in_(sorted(twin_ids)))
        .all()
    )
    return {str(rid): (str(so_line_id), qty, due) for rid, so_line_id, qty, due in rows}


def _verdict(db: Session, row: OrderInquiryRow, sheet_qty, sheet_date, restate_qty, restate_date) -> str:
    if row.state == INQUIRY_CANCELLED:
        return "cancelled"
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
    found: List[Squatter] = []
    seen = set()
    candidates = _candidates(db, inquiry_id)
    twins = _twins_on_their_lines(db, {str(c[9]) for c in candidates if c[9]})
    for (
        row, inquiry_no, line_no, line_qty, line_date, sheet, sheet_row, sheet_qty, sheet_date,
        twin_id, twin_sheet_row, skipped_sheet, skipped_sheet_row,
    ) in candidates:
        twin = twins.get(str(twin_id))
        # the twin must sit on ANOTHER line that is exactly what the sheet said
        if row.id in seen or twin is None or twin[0] == str(row.so_line_id):
            continue
        if (twin[1], twin[2]) != (sheet_qty, sheet_date):
            continue
        seen.add(row.id)
        found.append(
            Squatter(
                row_id=str(row.id), inquiry_no=inquiry_no, item_code=row.item_code,
                state=row.state, qty=row.qty, delivery_date=row.delivery_date, line_no=line_no,
                sheet=sheet, sheet_row=sheet_row, sibling_row_id=str(twin_id),
                sibling_sheet_row=twin_sheet_row, skipped_sheet=skipped_sheet,
                skipped_sheet_row=skipped_sheet_row, sheet_qty=sheet_qty, sheet_date=sheet_date,
                restate_qty=line_qty, restate_date=line_date,
                verdict=_verdict(db, row, sheet_qty, sheet_date, line_qty, line_date),
            )
        )
    return found


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
    row.note = (
        f"{row.note or ''}; Restated {now.date().isoformat()}: was {old['qty']} on "
        f"{old['delivery_date']}, a second copy of {hit.sheet} row {hit.sibling_sheet_row} "
        f"put on this line; now this line's own {hit.skipped_sheet} row {hit.skipped_sheet_row}"
    )
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
