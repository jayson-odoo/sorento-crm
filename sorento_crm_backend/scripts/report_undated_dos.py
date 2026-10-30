#!/usr/bin/env python3
"""Report the live delivery orders that have no DO date (DO-IMPORT-DATE).

Manual DOs can be imported without a date (owner, 30 Oct 2026); the import flags them and
reports leave them out until they have one (plan:
documentation/plans/order-management/PLAN-do-import-date.md). This is the to-fill list.
Print only - it never writes.

Run from sorento_crm_backend/:
    venv/bin/python scripts/report_undated_dos.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

_SQL = text(
    """
    SELECT o.id, o.company_id, o.order_number, o.order_type, o.created_at, o.actual_delivery_date, o.is_cancelled,
           o.doc_key IS NOT NULL AS from_autocount,
           (SELECT count(*) FROM order_lines ol WHERE ol.order_id = o.id) AS line_count
    FROM orders o
    WHERE o.order_date IS NULL AND o.deleted_at IS NULL
    ORDER BY o.created_at, o.order_number
    """
)


def undated_dos(conn) -> list[dict]:
    """Every live DO with no order_date, oldest first."""
    return [dict(r) for r in conn.execute(_SQL).mappings().all()]


def main() -> int:
    from app.database import engine

    with engine.connect() as conn:
        rows = undated_dos(conn)
    if not rows:
        print("No undated delivery orders.")
        return 0
    print(
        "order_number | type | created_at | actual_delivery | lines | cancelled | autocount | company_id"
    )
    for r in rows:
        print(
            f"{r['order_number']} | {r['order_type'] or '-'} | {r['created_at']:%Y-%m-%d %H:%M:%S} | "
            f"{r['actual_delivery_date'] or '-'} | {r['line_count']} | "
            f"{'yes' if r['is_cancelled'] else 'no'} | {'yes' if r['from_autocount'] else 'no'} | "
            f"{r['company_id']}"
        )
    print(f"\n{len(rows)} undated delivery order(s). They stay out of reports until their DO date is filled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
