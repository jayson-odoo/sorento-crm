#!/usr/bin/env python3
"""Write the `product_suppliers` link a manual code match should already have written.

WHY THIS EXISTS
---------------
`supplier_code_alias_service._ensure_product_supplier_link` used to compute the new link's
lead time as the MODE of the SUPPLIER's own existing `product_suppliers` rows and return
WITHOUT WRITING when the supplier had none - so a manual match on a supplier whose whole
universe came from the stock list (zero prior links) left "Their code" blank on the
product's Suppliers tab even though the match itself (the alias row) was recorded and
correctly carried the product into the plan universe. The function now falls back to the
PRODUCT's own links, then the system default, and always writes; this script repairs the
rows a manual match wrote under the old rule.

WHAT IT DOES
------------
For every `supplier_product_code_alias` row with `matched_by = 'manual'` and a `product_id`
set, that has no `(product_id, supplier_id)` row in `product_suppliers` yet, calls the same
`_ensure_product_supplier_link` the live match path calls - so the lead time picked here is
exactly the lead time a fresh match would pick today.

SAFETY / IDEMPOTENCY
--------------------
`--dry-run` is the DEFAULT. Nothing is written without `--apply`. Re-running is safe: once a
link exists, `_ensure_product_supplier_link` no-ops on it, so a second `--apply` reports zero
candidates.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_manual_alias_links.py
    venv/bin/python scripts/backfill_manual_alias_links.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product
from app.models.scm import SupplierProductCodeAlias
from app.services.scm.supplier_code_alias_service import _MANUAL, _ensure_product_supplier_link


def find_candidates(db: Session) -> List[SupplierProductCodeAlias]:
    """Every manual alias whose product has no `product_suppliers` row for that supplier."""
    linked = (
        db.query(ProductSupplier.product_id, ProductSupplier.supplier_id)
        .all()
    )
    linked_pairs = {(str(p), str(s)) for p, s in linked}

    rows = (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.matched_by == _MANUAL,
            SupplierProductCodeAlias.product_id.isnot(None),
        )
        .order_by(SupplierProductCodeAlias.created_at.asc())
        .all()
    )
    return [
        row
        for row in rows
        if (str(row.product_id), str(row.supplier_id)) not in linked_pairs
    ]


def run(db: Session, *, apply: bool) -> Dict[str, Any]:
    """Report (and optionally write) every missing link. The caller commits."""
    candidates = find_candidates(db)
    written = 0

    for row in candidates:
        supplier = db.query(Supplier).filter(Supplier.id == row.supplier_id).first()
        product = db.query(Product).filter(Product.id == row.product_id).first()
        supplier_label = supplier.supplier_name if supplier else row.supplier_id
        product_label = product.product_code if product else row.product_id

        if apply:
            _ensure_product_supplier_link(db, str(row.supplier_id), str(row.product_id))
            db.flush()
        link = (
            db.query(ProductSupplier)
            .filter(
                ProductSupplier.product_id == row.product_id,
                ProductSupplier.supplier_id == row.supplier_id,
            )
            .first()
        )
        lead_time = link.standard_lead_time_days if link is not None else None
        print(
            f"  supplier={supplier_label!r} code={row.supplier_code!r} "
            f"product={product_label!r} lead_time={lead_time}"
        )
        if apply and link is not None:
            written += 1

    return {"examined": len(candidates), "written": written}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the changes. Without this the script only reports.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only (the default; accepted so a run can say so out loud).",
    )
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET, which
    # is fail-closed and would return no rows at all. `None` is the sanctioned system /
    # all-companies scope; the alias and the product/supplier it names always share one
    # company (the alias's own FK chain), so there is nothing further to check here.
    set_company_scope(db, None)

    try:
        print(
            "Manual alias matches missing their product_suppliers link "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summary = run(db, apply=apply)
        if apply:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:      {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"examined:  {summary['examined']}")
        print(f"written:   {summary['written']}")
        if not apply and summary["examined"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
