#!/usr/bin/env python3
"""Backfill `suppliers.country_id` for the obvious Malaysian names (S2,
PLAN-local-supplier-oi-routing.md, AC-2.11, decision 8).

By NAME heuristic only: `SDN BHD` / `SDN. BHD.` / `(KL)` / `MALAYSIA`, case-insensitive,
whitespace-tolerant, matched ONLY where `country_id IS NULL` - a supplier already
carrying a country (Malaysian or not) is never touched, never overwritten. A supplier
whose name matches nothing (a Chinese factory, say) is left with no country at all;
this is a one-shot name sweep, not a resolver.

`run(db, *, apply=False) -> dict` with keys `matched`, `changed`, `samples` - shaped
after `scripts/backfill_product_supplier_from_last_po.py`'s `run(db, *, apply=False)`
contract: dry-run by default, idempotent (a second `--apply` run matches and changes
nothing), the caller's own ambient company scope, no scope of its own applied inside
`run()`.

Run from sorento_crm_backend/:
    python scripts/backfill_supplier_country.py --dry-run
    python scripts/backfill_supplier_country.py --apply
    python scripts/backfill_supplier_country.py --apply --company MOCHA
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, Dict, List

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.country import Country
from app.models.procurement import Supplier
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners

#: Whitespace-tolerant: `SDN. BHD.`, `SDN BHD`, `SDN.BHD` all match.
_MALAYSIAN_NAME = re.compile(r"SDN\.?\s*BHD\.?|\(KL\)|MALAYSIA", re.IGNORECASE)


def run(db, *, apply: bool = False, home_code: str = "MY") -> Dict[str, Any]:
    """The sweep itself, under the caller's own (already active) company scope.

    Returns ``matched`` (suppliers with no country whose name matches the heuristic),
    ``changed`` (rows actually written - 0 on a dry run) and ``samples`` (up to 10
    ``"<supplier_code> <supplier_name>"`` lines). Never touches a supplier that
    already carries a country, Malaysian or not.
    """
    home = db.query(Country).filter(Country.code.ilike(home_code)).first()
    if home is None:
        return {"matched": 0, "changed": 0, "samples": [], "home_country_found": False}

    candidates = (
        db.query(Supplier)
        .filter(Supplier.country_id.is_(None))
        .all()
    )
    matched_rows = [s for s in candidates if _MALAYSIAN_NAME.search(s.supplier_name or "")]

    samples: List[str] = [
        f"{s.supplier_code} {s.supplier_name}" for s in matched_rows[:10]
    ]
    changed = 0
    if apply:
        for supplier in matched_rows:
            supplier.country_id = home.id
            changed += 1
        db.commit()

    return {
        "matched": len(matched_rows),
        "changed": changed,
        "samples": samples,
        "home_country_found": True,
    }


def _print_report(report: Dict[str, Any]) -> None:
    print(f"matched: {report['matched']}")
    print(f"changed: {report['changed']}")
    for line in report["samples"]:
        print(f"  {line}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write the changes. Default is dry-run."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicit dry-run (also the default)."
    )
    parser.add_argument(
        "--company", default=None, help="Company CODE to run against (default: incumbent)."
    )
    args = parser.parse_args()
    apply_changes = bool(args.apply)

    register_company_scope_listeners()

    db = SessionLocal()
    company_id = DEFAULT_COMPANY_ID
    if args.company:
        company = db.query(Company).filter(Company.code == args.company).first()
        if company is None:
            print(f"no company with code {args.company!r}")
            db.close()
            return 1
        company_id = str(company.id)
    print(f"company scope: {args.company or 'incumbent'} ({company_id})")
    print(f"mode: {'APPLY' if apply_changes else 'DRY-RUN (no writes)'}")

    try:
        with company_scope(db, frozenset({company_id})):
            report = run(db, apply=apply_changes)
            if not report["home_country_found"]:
                print("no MY row in countries - run the 510_countries migration first.")
                return 1
            _print_report(report)
            return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
