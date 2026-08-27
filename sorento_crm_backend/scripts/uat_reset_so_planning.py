"""Put one sales order back to never-planned on a dev copy, by SO number.

The same reset the Sales Orders page offers under Actions > Reset planning
(`app.services.scm.planning_reset_service`); this is its command line. Dry run by default.

    venv/bin/python -m scripts.uat_reset_so_planning --so SO381895
    venv/bin/python -m scripts.uat_reset_so_planning --so SO381895 --rewind-book --apply
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.database import SessionLocal
from app.services.scm.planning_reset_service import reset_planning


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", required=True, help="SO number, e.g. SO381895")
    ap.add_argument("--apply", action="store_true", help="really delete (default: dry run)")
    ap.add_argument("--rewind-book", action="store_true",
                    help="restore lines moved by planning-change batches from their from_json")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        core = db.execute(text("SELECT id FROM sales_orders WHERE so_number = :n"), {"n": args.so}).all()
        if len(core) != 1:
            print(f"{args.so}: expected one core sales order, found {len(core)}"); return 2
        result = reset_planning(db, str(core[0][0]), rewind_book=args.rewind_book, apply=args.apply)
        print(json.dumps(result, indent=2))
        print("applied." if args.apply else "dry run: nothing changed. Add --apply.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
