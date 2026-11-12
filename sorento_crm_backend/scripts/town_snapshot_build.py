#!/usr/bin/env python3
"""Build one town snapshot by hand (SORENTO-TOWN), for testing a copy whose data ends before today.

Run from sorento_crm_backend/ with the copy's env:
    venv/bin/python -m scripts.town_snapshot_build                       # today, as of now (MYT)
    venv/bin/python -m scripts.town_snapshot_build --date 2026-11-03 --at 15:42
    venv/bin/python -m scripts.town_snapshot_build --date 2026-11-03 --at 15:42 --as-today

`--as-today` stores the snapshot under TODAY's Redis keys so the /town page serves it. That is for
local and test copies only: it refuses when ENVIRONMENT says production. The script uses
`build_snapshot` and `store` on an ordinary session and does not take the scheduler lock.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from typing import Optional

from app.config import settings
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.town import snapshot as town

PRODUCTION_NAMES = {"production", "prod"}


def run(db, redis, company_id: str, day: date, now: datetime, *, as_today: bool) -> tuple:
    """Build `day` as of `now` and store it; returns `(day it was stored under, version)`."""
    full = town.build_snapshot(db, company_id, day, now=now)
    stored_day = datetime.now(town.MYT).date() if as_today else day
    return stored_day, town.store(redis, company_id, stored_day, full)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Build one town snapshot by hand.")
    parser.add_argument("--date", help="the day to build, YYYY-MM-DD (default: today, MYT)")
    parser.add_argument("--at", help="the time of day to build it as of, HH:MM MYT (default: now)")
    parser.add_argument("--as-today", action="store_true", help="store under today's keys (local and test copies only)")
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    args = parser.parse_args(argv)

    if args.as_today and settings.environment.strip().lower() in PRODUCTION_NAMES:
        print("Refusing --as-today: ENVIRONMENT says production.", file=sys.stderr)
        return 2
    if args.as_today:
        print("WARNING: --as-today stores a snapshot under today's keys. Local and test copies only.", file=sys.stderr)

    now = datetime.now(town.MYT)
    day = date.fromisoformat(args.date) if args.date else now.date()
    if args.date or args.at:
        at = time.fromisoformat(args.at) if args.at else time(23, 59)
        now = datetime.combine(day, at, tzinfo=town.MYT)

    from app.database import SessionLocal
    from app.services.queue_service import redis_conn

    db = SessionLocal()
    set_company_scope(db, None)  # the build filters by company itself
    try:
        stored_day, version = run(db, redis_conn, args.company_id, day, now, as_today=args.as_today)
    finally:
        db.close()
    print(f"Stored {day} as of {now:%H:%M} under {stored_day} (version {version[:8]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
