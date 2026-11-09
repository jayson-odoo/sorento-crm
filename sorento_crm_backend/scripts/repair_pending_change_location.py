"""SO-LOCATION-GAP one-off repair (owner, 9 Nov 2026, option a).

A PENDING planning-change row written before the SO-LOCATION-GAP fix carries no location when
AutoCount moved its line in an EARLIER push (before #2221 detected moves; prod SO429664
SRTWT8239-GM, confirmed at BRW, now BRW-BB, a date change pending). The "What changed" lightbox
then shows only the date and the Confirm Review split shows no NEW LOCATION, while the email's
REMARK says "NEW LOCATION (was BRW)".

This gives each such row what a row written now carries (`planning_change_service.
carry_planned_location`, the one rule): `from.location` = where the line was last confirmed
(else where its live ORDER rows sit), `to.location` = where it is now. Only pending rows, only
those two keys; nothing else on the row changes. A repaired row carries a location, so a second
run finds nothing.

Dry run is the default. `run()` does not commit; `main()` does, after `run()` returns.

Run from sorento_crm_backend/:
    venv/bin/python scripts/repair_pending_change_location.py            # dry run
    venv/bin/python scripts/repair_pending_change_location.py --apply    # write
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.inventory import Warehouse  # noqa: E402
from app.models.order import SalesOrderLine  # noqa: E402
from app.models.planning_change import (  # noqa: E402
    PLANNING_CHANGE_STATE_PENDING,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine  # noqa: E402
from app.services.planning_change_service import (  # noqa: E402
    carry_planned_location,
    confirmed_locations,
)
from app.services.project_line_split_service import display_line_nos  # noqa: E402
from app.services.project_supply_service import ProjectSupplyService  # noqa: E402


def _pending_rows(db: Session) -> List[PlanningChangeRow]:
    """Pending as the Review split reads it (`LineSplitService.pending_from_by_line`): the
    batch unapplied and the row still pending."""
    return (
        db.query(PlanningChangeRow)
        .join(PlanningChangeBatch, PlanningChangeBatch.id == PlanningChangeRow.batch_id)
        .filter(
            PlanningChangeBatch.applied_at.is_(None),
            PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_PENDING,
            PlanningChangeRow.project_line_id.isnot(None),
        )
        .order_by(PlanningChangeRow.created_at.asc(), PlanningChangeRow.id.asc())
        .all()
    )


def _now_locations(db: Session, line_ids: List[str]) -> Dict[str, str]:
    """`project line id -> core warehouse code`: where AutoCount has the line now (what the
    board and the Review split read)."""
    if not line_ids:
        return {}
    return {
        str(line_id): code
        for line_id, code in db.query(ProjectSalesOrderLine.id, Warehouse.warehouse_code)
        .join(SalesOrderLine, SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id)
        .join(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(ProjectSalesOrderLine.id.in_(line_ids))
        if code
    }


def run(db: Session, *, apply: bool) -> dict:
    """Find, print, and (with `apply`) write. Never commits."""
    rows = _pending_rows(db)
    line_ids = sorted({str(row.project_line_id) for row in rows})
    now = _now_locations(db, line_ids)
    numbers = display_line_nos(db, line_ids) if line_ids else {}
    supply = ProjectSupplyService(db)
    confirmed_by_order: Dict[str, Dict[str, Optional[str]]] = {}
    so_numbers: Dict[str, str] = {}
    found = []
    for row in rows:
        pso_id = str(row.project_sales_order_id)
        if pso_id not in confirmed_by_order:
            confirmed_by_order[pso_id] = confirmed_locations(supply.active_decision(pso_id))
            order = db.get(ProjectSalesOrder, pso_id)
            so_numbers[pso_id] = (
                (order.autocount_doc_no or order.provisional_ref or pso_id) if order else pso_id
            )
        line_id = str(row.project_line_id)
        new_from, new_to = carry_planned_location(
            db, row.from_json or {}, row.to_json or {},
            kind=row.kind,
            project_line_id=line_id,
            confirmed=confirmed_by_order[pso_id],
            now_location=now.get(line_id),
        )
        if new_from.get("location") == (row.from_json or {}).get("location"):
            continue
        found.append((row, new_from, new_to))
        print(
            f"  {so_numbers[pso_id]} line {numbers.get(line_id, row.line_no)} "
            f"{row.item_code} ({row.kind}): location {new_from['location']} -> "
            f"{new_to['location']} [{row.id}]"
        )
    print(f"found {len(found)} pending change rows missing their location move")
    result = {"found": len(found), "repaired": 0}
    if not apply:
        return result
    for row, new_from, new_to in found:
        row.from_json = new_from
        row.to_json = new_to
    db.flush()
    result["repaired"] = len(found)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run(db, apply=args.apply)
        if not args.apply:
            db.rollback()
            print("\nDry run only - nothing written. Re-run with --apply to write.")
            return 0
        db.commit()
        print(f"\nCommitted: {result['repaired']} rows repaired.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
