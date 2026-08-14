#!/usr/bin/env python3
"""Mark a company's existing discontinued products as already reported.

Run from sorento_crm_backend/:
    python scripts/stamp_discontinued_backlog.py --company MCH          # dry run
    python scripts/stamp_discontinued_backlog.py --company MCH --apply

Run this ONCE, immediately before adding a company to
``system_settings.product_discontinued_notify_company_ids``.

`product_discontinued_check` reports products where ``discontinued_notified_at IS
NULL``. On a company that has never been reported on, that is the company's entire
history - so the first tick after opting it in sends one notification titled
"2716 products discontinued", listing a catalogue nobody just changed. Stamping the
backlog first makes that tick a no-op, and only products discontinued AFTER the
cutover notify.

This is a script rather than a migration on purpose: it is a per-company operational
step tied to when someone decides to switch a company on, not a schema change that
every environment must run at the same point in history.

``discontinued_notify_batch_id`` is deliberately left NULL - these rows were never
part of a real batch, and pointing them at a fabricated one would make that batch's
drill-down lie about what was sent.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.product import Product  # noqa: E402


def _resolve_company(db, ref: str) -> Company:
    ref = (ref or "").strip()
    row = (
        db.query(Company)
        .filter((Company.code == ref) | (Company.name == ref) | (Company.id == ref))
        .first()
    )
    if row is None:
        available = ", ".join(f"{c.code} ({c.name})" for c in db.query(Company).all())
        raise SystemExit(f"No company matches {ref!r}. Available: {available}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True, help="code, name or id")
    ap.add_argument("--apply", action="store_true", help="write; omit for a dry run")
    args = ap.parse_args()

    db = SessionLocal()
    # Products are company-scoped; the scheduler reads them with scope=None and so
    # does this script - the company filter below is explicit.
    set_company_scope(db, None)
    try:
        company = _resolve_company(db, args.company)
        q = db.query(Product).filter(
            Product.is_discontinued.is_(True),
            Product.discontinued_notified_at.is_(None),
            Product.company_id == company.id,
        )
        pending = q.count()
        print(f"company : {company.name} ({company.code}) {company.id}")
        print(f"pending : {pending} discontinued product(s) never reported")

        if pending == 0:
            print("\nNothing to stamp - the first tick after opting in will be quiet.")
            return 0
        if not args.apply:
            print("\nDRY RUN - nothing written. Re-run with --apply.")
            return 0

        now = datetime.utcnow()
        updated = q.update(
            {Product.discontinued_notified_at: now}, synchronize_session=False
        )
        db.commit()
        print(f"\nStamped {updated} product(s). Safe to opt {company.code} in now.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
