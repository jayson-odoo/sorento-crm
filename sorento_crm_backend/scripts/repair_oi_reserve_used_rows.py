#!/usr/bin/env python3
"""Move open reserve requests off used order inquiry rows onto their line's live row.

OI-RESERVE-USED-ROW (`documentation/plans/scm/PLAN-oi-reserve-used-row-04nov.md`).

WHY THIS EXISTS
----------------
The stock debt snapshot drill offered a used row (`redirected_to_pool`: its line changed after
its goods arrived, so it was kept as history and a fresh row raised) in "Request CS to reserve".
A request stored there is one CS never reserves: they reserve against the live row (prod
OI-2609-0257 / SO396347 / SRTSA830-PJ: 33 asked on the used 55 row, not the live 33 row).
`create_request` now refuses a used row; this moves the requests already stuck.

WHAT IT FINDS (read-only)
--------------------------
Every request row still unanswered (`qty_reserved` null) on a request still open (`requested`)
whose OI row is not live (used, or cancelled: `oi_row_visibility`).

WHAT IT WRITES (`--apply`)
---------------------------
`row_id` of the request row moves to the ONE live row of the same OI on the same sales order
line, when that row has no open request of its own, is not already on this request, and its
requestable qty (`_requestable`) covers the qty asked. Qty, location, requester, request date and
park state are untouched. One audit EVENT per moved row. Anything else is printed with the
reason it is held and left for a person.

SAFETY / IDEMPOTENCY
---------------------
Dry run is the default. `--apply` needs `--expect N`, the move count the dry run printed, and
writes nothing when the count found at apply time differs. A moved row sits on a live row, so a
second run does not find it. `run()` never commits; `main()` does, after `run()` returns.

Run from sorento_crm_backend/:
    venv/bin/python scripts/repair_oi_reserve_used_rows.py
    venv/bin/python scripts/repair_oi_reserve_used_rows.py --inquiry-no OI-2609-0257
    venv/bin/python scripts/repair_oi_reserve_used_rows.py --apply --expect 1
"""

import argparse
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, not_, or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.project_so import (  # noqa: E402
    RESERVE_REQUESTED,
    OrderInquiry,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.services.audit_service import log_audit  # noqa: E402
from app.services.oi_row_visibility import live_row_clause  # noqa: E402
from app.services.order_inquiry_reserve_service import (  # noqa: E402
    _open_request_row_ids,
    _requestable,
)

MOVE = "move"
_EVENT = "oi_reserve_used_row_repair"


class CountMismatch(Exception):
    """`--apply` found a different number of rows to move than `--expect` names."""


@dataclass
class Stuck:
    request_row_id: str
    request_id: str
    request_no: int
    inquiry_no: str
    item_code: Optional[str]
    from_row_id: str
    from_qty: Decimal
    qty_requested: Decimal
    to_row_id: Optional[str]
    to_qty: Optional[Decimal]
    verdict: str


def _num(value) -> str:
    value = Decimal(value)
    return str(int(value)) if value == value.to_integral_value() else str(value.normalize())


def _live_siblings(db: Session, row: OrderInquiryRow) -> List[OrderInquiryRow]:
    """Live rows of the same OI on the same sales order line: the mirror line itself, or any
    mirror of the same core line (a revision may re-mirror it)."""
    if row.so_line_id is None:
        return []
    core_id = (
        db.query(ProjectSalesOrderLine.core_sales_order_line_id)
        .filter(ProjectSalesOrderLine.id == row.so_line_id)
        .scalar()
    )
    same_line = [OrderInquiryRow.so_line_id == row.so_line_id]
    if core_id is not None:
        same_line.append(
            OrderInquiryRow.so_line_id.in_(
                db.query(ProjectSalesOrderLine.id).filter(
                    ProjectSalesOrderLine.core_sales_order_line_id == core_id
                )
            )
        )
    return (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.order_inquiry_id == row.order_inquiry_id,
            OrderInquiryRow.id != row.id,
            or_(*same_line),
            live_row_clause(),
        )
        .order_by(OrderInquiryRow.created_at, OrderInquiryRow.id)
        .all()
    )


def find_stuck(db: Session, *, inquiry_id: Optional[str] = None) -> List[Stuck]:
    query = (
        db.query(OrderInquiryReserveRequestRow, OrderInquiryReserveRequest, OrderInquiryRow, OrderInquiry)
        .join(
            OrderInquiryReserveRequest,
            OrderInquiryReserveRequest.id == OrderInquiryReserveRequestRow.request_id,
        )
        .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryReserveRequestRow.row_id)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(
            OrderInquiryReserveRequestRow.qty_reserved.is_(None),
            OrderInquiryReserveRequest.state == RESERVE_REQUESTED,
            not_(live_row_clause()),
        )
    )
    if inquiry_id is not None:
        query = query.filter(OrderInquiry.id == inquiry_id)
    found: List[Stuck] = []
    for rr, request, row, inquiry in query.all():
        siblings = _live_siblings(db, row)
        target = siblings[0] if len(siblings) == 1 else None
        verdict = MOVE
        if not siblings:
            verdict = "no live row on the line"
        elif len(siblings) > 1:
            verdict = f"{len(siblings)} live rows on the line"
        elif target.id in _open_request_row_ids(db, [target.id]):
            verdict = "live row has its own open request"
        elif (
            db.query(func.count(OrderInquiryReserveRequestRow.id))
            .filter(
                OrderInquiryReserveRequestRow.request_id == request.id,
                OrderInquiryReserveRequestRow.row_id == target.id,
            )
            .scalar()
        ):
            verdict = "live row already on this request"
        elif _requestable(db, target) < Decimal(rr.qty_requested):
            verdict = f"live row has only {_num(_requestable(db, target))} to request"
        found.append(
            Stuck(
                request_row_id=str(rr.id),
                request_id=str(request.id),
                request_no=request.ordinal,
                inquiry_no=inquiry.inquiry_no,
                item_code=row.item_code,
                from_row_id=str(row.id),
                from_qty=Decimal(row.qty),
                qty_requested=Decimal(rr.qty_requested),
                to_row_id=str(target.id) if target is not None else None,
                to_qty=Decimal(target.qty) if target is not None else None,
                verdict=verdict,
            )
        )
    return sorted(found, key=lambda s: (s.inquiry_no or "", s.item_code or "", s.request_no))


def _move(db: Session, hit: Stuck) -> None:
    rr = db.get(OrderInquiryReserveRequestRow, hit.request_row_id)
    rr.row_id = hit.to_row_id
    log_audit(
        db,
        "project_order_inquiry_reserve_request_rows",
        str(rr.id),
        "EVENT",
        event=_EVENT,
        old_values={"row_id": hit.from_row_id},
        new_values={"row_id": hit.to_row_id, "qty_requested": _num(hit.qty_requested)},
        company_id=rr.company_id,
        reason="OI-RESERVE-USED-ROW",
        skip_flush=True,
    )


def run(db: Session, *, apply: bool, expect: Optional[int], inquiry_id: Optional[str] = None) -> dict:
    """Find, print, and (with `apply`) move. Never commits."""
    found = find_stuck(db, inquiry_id=inquiry_id)
    to_move = [hit for hit in found if hit.verdict == MOVE]
    for hit in found:
        target = f"live row {_num(hit.to_qty)}" if hit.to_qty is not None else "no target"
        print(
            f"  {hit.inquiry_no} {hit.item_code} request #{hit.request_no}: "
            f"{_num(hit.qty_requested)} asked on used row {_num(hit.from_qty)} -> {target}: "
            f"{hit.verdict} [{hit.request_row_id}]"
        )
    held = len(found) - len(to_move)
    print(f"found {len(found)}: move {len(to_move)}, held {held}")
    result = {"found": len(found), "move": len(to_move), "held": held, "moved": 0}
    if not apply:
        return result
    if expect is None or expect != len(to_move):
        raise CountMismatch(
            f"--expect {expect} but {len(to_move)} rows would be moved now; "
            "re-run the dry run and pass the count it prints"
        )
    for hit in to_move:
        _move(db, hit)
    db.flush()
    result["moved"] = len(to_move)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    parser.add_argument("--expect", type=int, help="With --apply: the dry run's move count.")
    parser.add_argument("--inquiry-no", help="Restrict to one inquiry, e.g. OI-2609-0257.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        inquiry_id = None
        if args.inquiry_no:
            inquiry = (
                db.query(OrderInquiry).filter(OrderInquiry.inquiry_no == args.inquiry_no).one_or_none()
            )
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
            print(
                "\nDry run only, nothing written. Re-run with --apply --expect "
                f"{result['move']} to write."
            )
            return 0
        db.commit()
        print(f"\nCommitted: {result['moved']} request rows moved.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
