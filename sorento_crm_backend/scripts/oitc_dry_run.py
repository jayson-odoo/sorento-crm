#!/usr/bin/env python3
"""Dry run of `alembic/versions/oitc_0001_fake_reconfirms.py` (lane OI-TRAIL-CLEANUP).

Runs the migration's own `clean_fake_reconfirms` inside one transaction, prints its counts
and the decision trail of the named sales orders before and after, then ROLLS BACK. Run it
only against a throwaway copy; `alembic upgrade head` is what applies the change for real.

    DATABASE_URL=postgresql://.../throwaway python -m scripts.oitc_dry_run SO400884
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "oitc_0001_fake_reconfirms.py"
)


def _cleanup_module():
    spec = importlib.util.spec_from_file_location("oitc_0001_fake_reconfirms", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _print_trails(db, so_numbers) -> None:
    from app.models.order import SalesOrder, SalesOrderLine
    from app.services.decision_trail_service import DecisionTrailService

    lines = (
        db.query(SalesOrder.so_number, SalesOrderLine.id)
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .filter(SalesOrder.so_number.in_(so_numbers))
        .order_by(SalesOrder.so_number, SalesOrderLine.id)
        .all()
    )
    for so_number, line_id in lines:
        for entry in DecisionTrailService(db).for_core_line(str(line_id)):
            if entry["kind"] in ("sheet", "raised", "reconfirmed"):
                print(f"  {so_number} {entry['kind']:<11} {entry['at']}  "
                      f"{entry['actor_name'] or '-'}  {entry['detail']}")


#: What the cleanup could still have missed (reviewer, should-fix 2): a reconfirm in the
#: header's own raiser's name ~8 h after its first row (e.g. an upload rolled back by
#: `scripts/rollback_oi_sheet_upload.py` before 523 ran, so no row kept its stamp), and a
#: sheet row still acknowledged ~8 h after its birth. Both expected 0, or explained.
_LEFTOVERS = {
    "suspect_reconfirms_left": """
        SELECT COUNT(*) FROM projects.order_inquiry_raises r
        JOIN projects.order_inquiries h ON h.id = r.order_inquiry_id
        JOIN (SELECT order_inquiry_id, MIN(created_at) AS first_at
              FROM projects.order_inquiry_rows GROUP BY order_inquiry_id) f
          ON f.order_inquiry_id = r.order_inquiry_id
        WHERE r.kind = 'reconfirmed' AND r.raised_by = h.raised_by
          AND r.raised_at - f.first_at BETWEEN interval '7 hours 50 minutes'
                                           AND interval '9 hours'
    """,
    "sheet_rows_still_shifted": """
        SELECT COUNT(*) FROM projects.order_inquiry_rows
        WHERE note LIKE 'Migrated from order inquiry sheet%%'
          AND acknowledged_at - created_at BETWEEN interval '7 hours 50 minutes'
                                               AND interval '9 hours'
    """,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("so_numbers", nargs="*", default=["SO400884"])
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        print("BEFORE")
        _print_trails(db, args.so_numbers)
        print("COUNTS", _cleanup_module().clean_fake_reconfirms(db.connection()))
        db.expire_all()
        print("LEFTOVERS", {
            name: db.connection().exec_driver_sql(sql).scalar()
            for name, sql in _LEFTOVERS.items()
        })
        print("AFTER")
        _print_trails(db, args.so_numbers)
    finally:
        db.rollback()
        db.close()
        print("rolled back")


if __name__ == "__main__":
    main()
