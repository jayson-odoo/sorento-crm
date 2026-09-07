#!/usr/bin/env python3
"""Backfill orders that carry a delivery date but never advanced past NEW.

PLAN-do-search-and-mcp-feedback-7sep §2: measured on the prod copy (7 Sep 2026),
4,833 orders carry `actual_delivery_date` under status NEW - all written by the
Excel tracking import before the `already_delivered` guard (commit 9c3acb004,
5 Aug) stopped new damage. Nothing derives status from the date, so the
existing rows stay wrong until repaired here.

Rule: `order_status = NEW AND actual_delivery_date IS NOT NULL AND deleted_at
IS NULL` -> `order_status = DELIVERED`. Only NEW is touched: CANCELLED,
PENDING and any other non-delivered status with a date are left alone (not
the reported defect).

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/backfill_delivered_status.py            # dry-run, writes nothing
    python scripts/backfill_delivered_status.py --apply    # writes, prints before/after counts

Idempotent: a second `--apply` run reports zero candidates.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.models.order import Order, OrderStatus


def backfill(db, apply: bool) -> dict:
    """Core logic, isolated from CLI/session plumbing so it is unit-testable.

    Returns `{"candidates": n, "updated": m}`: `candidates` is the count of
    NEW+dated+not-deleted rows found before any write; `updated` is the count
    actually flipped to DELIVERED (0 on a dry run).
    """
    new_id = (
        db.query(OrderStatus.id)
        .filter(func.lower(OrderStatus.status_code) == "new")
        .scalar()
    )
    delivered_id = (
        db.query(OrderStatus.id)
        .filter(func.lower(OrderStatus.status_code) == "delivered")
        .scalar()
    )
    if not new_id or not delivered_id:
        return {"candidates": 0, "updated": 0}

    query = db.query(Order).filter(
        Order.order_status_id == new_id,
        Order.actual_delivery_date.is_not(None),
        Order.deleted_at.is_(None),
    )
    candidates = query.count()

    updated = 0
    if apply and candidates:
        updated = query.update(
            {Order.order_status_id: delivered_id}, synchronize_session=False
        )
        db.commit()

    return {"candidates": candidates, "updated": updated}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Write the change. Default is dry-run."
    )
    args = parser.parse_args()

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET,
    # which is fail-closed and would return no rows at all. `None` is the sanctioned
    # system / all-companies scope; every DO across every company gets the same rule.
    set_company_scope(db, None)
    try:
        result = backfill(db, apply=args.apply)
        if args.apply:
            print(
                f"Done. {result['candidates']} candidate(s) found, "
                f"{result['updated']} order(s) set to DELIVERED."
            )
            after = backfill(db, apply=False)
            print(f"Re-check: {after['candidates']} candidate(s) remain.")
        else:
            print(
                f"[dry-run] {result['candidates']} order(s) would be set to "
                "DELIVERED. No writes."
            )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
