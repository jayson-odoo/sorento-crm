"""Run one DB retention rule by hand and time it (PLAN-db-retention-12nov).

Calls the same rule the scheduled task runs, with the system_settings knobs; the flags
below override them. Dry-run (count only) unless --apply.

Usage:
  cd sorento_crm_backend && venv/bin/python -m app.scripts.run_data_retention --rule plan_exception_prune
  venv/bin/python -m app.scripts.run_data_retention --rule plan_exception_prune --apply --batch-size 5000 --sleep-ms 200
"""
from __future__ import annotations

import argparse
import json
import time

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.services.data_retention_service import RULES, run_retention_rule


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one DB retention rule")
    parser.add_argument("--rule", required=True, choices=sorted(RULES), help="Scheduled task key")
    parser.add_argument("--apply", action="store_true", help="Delete for real (default: count only)")
    parser.add_argument("--batch-size", type=int, default=None, help="Rows per batch (default: setting)")
    parser.add_argument("--sleep-ms", type=int, default=None, help="Pause between batches (default: setting)")
    parser.add_argument("--max-minutes", type=float, default=None, help="Time budget (default: setting)")
    args = parser.parse_args()

    db = SessionLocal()
    # A bare SessionLocal() has no company scope and fail-closes; a task run sees every company.
    set_company_scope(db, None)
    started = time.monotonic()
    try:
        result = run_retention_rule(
            db,
            args.rule,
            dry_run=not args.apply,
            batch_size=args.batch_size,
            sleep_ms=args.sleep_ms,
            max_seconds=None if args.max_minutes is None else args.max_minutes * 60.0,
        )
    finally:
        db.close()
    print(json.dumps(result, default=str))
    print(f"elapsed_seconds: {time.monotonic() - started:.1f}")


if __name__ == "__main__":
    main()
