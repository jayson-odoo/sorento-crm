#!/usr/bin/env python3
"""Backfill `product_suppliers` so its primary link agrees with the product's own last
purchase order (S15, PLAN-reorder-feedback-9sep.md, ruling 2, 10 Sep 2026).

ROOT CAUSE
----------
`resolve_default_supplier_id` (`app/services/rules/product_rules.py`) auto-links every
new or imported product to `system_settings.default_product_supplier_id`, or the OLDEST
supplier by `created_at` when nothing is configured, on create/import
(`link_default_supplier`). On the prod copy that oldest supplier is the code DEFAULT, and
11,804 of the table's 11,807 `product_suppliers` rows point at it, none marked primary.
The Summary Order Report's Supplier column (`summary_order_service._last_po_supplier_map`,
S15) has since stopped reading this link table for exactly that reason and reads purchase
order history instead - but the link table itself is unchanged data, and a caller that
still reads it (a future report, an operator query) would keep seeing DEFAULT. This
script repairs the link table to agree with the same measured fact: of the 5,353 products
with PO history, only 1 already had a `product_suppliers` link matching its own last PO.

WHAT IT DOES
------------
For each product with at least one purchase-order line, finds the supplier of its NEWEST
PO line (`purchase_orders.issue_date` desc, NULLs last, `created_at` desc as the
tiebreak - the same ordering `_last_po_supplier_map` uses). Per product:

* If a `product_suppliers` link to that supplier already exists, it is promoted:
  `is_primary_supplier` set True (a "promoted" link).
* Else a new link is CREATED: `is_primary_supplier=True`,
  `standard_lead_time_days=resolve_standard_lead_time_days(settings)` (the same default a
  fresh manual/import link gets), `moq`/`order_multiple`/`unit_cost`/`currency` left NULL -
  nothing here invents a commercial term nobody has stated (a "created" link).
* Every OTHER link of that product has `is_primary_supplier` cleared - never anything
  else on it (not its moq, cost, lead time) - so the product ends with exactly one
  primary link, the last-PO supplier's.
* The product's own link to the DEFAULT supplier (identified by `default_supplier_code`,
  exact match on `suppliers.supplier_code`) is then DELETED, UNLESS the last-PO supplier
  IS the DEFAULT supplier itself (a product genuinely last bought from DEFAULT keeps that
  one link, now primary, and nothing is deleted).

`drop_default_all=True` (CLI: `--drop-default-all`) additionally deletes the DEFAULT link
of every product that has NO PO history at all (nothing to promote it to, so the link is
simply removed). Without it those products are left exactly as they are - a product this
script cannot say anything about is not touched.

A link to any supplier OTHER than DEFAULT and the resolved last-PO supplier is never
touched beyond its own `is_primary_supplier` flag - its moq, cost, lead time and currency
are the buyer's own data and this script states no opinion on them.

SAFETY / IDEMPOTENCY
---------------------
- `--dry-run` (the default) writes nothing and returns/prints the per-product plan plus
  the summary counts. `--apply` is required to write.
- Re-running after `--apply` is a no-op: the target link is already primary (0 promoted,
  0 created) and the DEFAULT link is already gone (0 removed).
- `--company` pins one company for the run, same as
  `scripts/backfill_grn_spo_allocation_links.py` beside it (see COMPANY SCOPE below).

COMPANY SCOPE
-------------
`products`, `product_suppliers`, `suppliers`, `purchase_orders` and `purchase_order_lines`
are all company-scoped, and a plain `python scripts/...` process never runs the app's
startup path, so the ORM's own company-scope listener is not installed and the session's
scope is UNSET (fail-closed, `1=0`). `main()` registers the listener itself and pins ONE
company for the whole run before calling `run()`; the newest-PO-line lookup is raw SQL and
states its own `company_sql_predicate` for the same reason `summary_order_service`'s own
raw queries do. `--company <code>` selects it; without it the incumbent company
(`company_scope.DEFAULT_COMPANY_ID`) is used, which is where every pre-multi-company row
lives. A caller that already holds an active company scope (a test, `pg_session`) calls
`run(db, ...)` directly and skips `main()`'s scope setup entirely.

Run from sorento_crm_backend/:
    python scripts/backfill_product_supplier_from_last_po.py --dry-run
    python scripts/backfill_product_supplier_from_last_po.py --apply
    python scripts/backfill_product_supplier_from_last_po.py --apply --drop-default-all
    python scripts/backfill_product_supplier_from_last_po.py --apply --company MOCHA
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from typing import Any, Dict, List, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import ProductSupplier, Supplier
from app.models.user import SystemSetting
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_sql import company_sql_predicate
from app.services.rules.product_rules import resolve_standard_lead_time_days


def _last_po_suppliers(db) -> List[Tuple[str, str, str, str]]:
    """``[(product_id, product_code, supplier_id, supplier_code)]`` - one row per product
    with PO history, the supplier of its newest PO line. Same ordering
    `summary_order_service._last_po_supplier_map` uses."""
    co, co_params = company_sql_predicate(db, "pol.company_id", param_prefix="bkfl")
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (pol.product_id) pol.product_id::text AS pid,
               p.product_code, po.supplier_id::text AS supplier_id, s.supplier_code
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        JOIN suppliers s ON s.id = po.supplier_id
        JOIN products p ON p.id = pol.product_id
        WHERE 1=1 {("AND " + co) if co else ""}
        ORDER BY pol.product_id, po.issue_date DESC NULLS LAST, po.created_at DESC
    """), co_params).fetchall()
    return [(pid, code, sid, scode) for pid, code, sid, scode in rows]


def run(
    db,
    *,
    apply: bool = False,
    drop_default_all: bool = False,
    default_supplier_code: str = "DEFAULT",
) -> Dict[str, Any]:
    """The sweep itself, under the caller's own (already active) company scope.

    Returns a report dict: ``products_seen``, ``created``, ``promoted``,
    ``default_removed``, ``default_all_removed``, ``samples`` (up to 10
    ``"<product_code> -> <supplier_code> (created|promoted)"`` lines). `apply=False`
    (the default) writes nothing - every count is still the plan that WOULD be applied.
    """
    settings = db.query(SystemSetting).first()
    default_supplier = (
        db.query(Supplier)
        .filter(Supplier.supplier_code == default_supplier_code)
        .first()
    )
    default_supplier_id = str(default_supplier.id) if default_supplier else None

    last_po = _last_po_suppliers(db)
    products_seen = len(last_po)
    created = 0
    promoted = 0
    default_removed = 0
    samples: List[str] = []

    products_with_po = {pid for pid, _c, _s, _sc in last_po}

    for product_id, product_code, supplier_id, supplier_code in last_po:
        links = (
            db.query(ProductSupplier)
            .filter(ProductSupplier.product_id == product_id)
            .all()
        )
        by_supplier = {str(l.supplier_id): l for l in links}
        target = by_supplier.get(supplier_id)

        if target is None:
            if len(samples) < 10:
                samples.append(f"{product_code} -> {supplier_code} (created)")
            created += 1
            if apply:
                target = ProductSupplier(
                    id=str(uuid.uuid4()),
                    product_id=product_id, supplier_id=supplier_id,
                    is_primary_supplier=True,
                    standard_lead_time_days=resolve_standard_lead_time_days(settings),
                )
                db.add(target)
                db.flush()
        elif not target.is_primary_supplier:
            if len(samples) < 10:
                samples.append(f"{product_code} -> {supplier_code} (promoted)")
            promoted += 1
            if apply:
                target.is_primary_supplier = True

        # Clear primary on every OTHER link of this product - the flag only, nothing else.
        if apply:
            for sid, link in by_supplier.items():
                if sid != supplier_id and link.is_primary_supplier:
                    link.is_primary_supplier = False

        # The product's own DEFAULT link is removed unless DEFAULT is itself the
        # last-PO supplier (then it was just promoted above, not deleted).
        default_link = by_supplier.get(default_supplier_id) if default_supplier_id else None
        if default_link is not None and supplier_id != default_supplier_id:
            default_removed += 1
            if apply:
                db.delete(default_link)

        if apply:
            db.flush()

    default_all_removed = 0
    if drop_default_all and default_supplier_id:
        query = db.query(ProductSupplier).filter(
            ProductSupplier.supplier_id == default_supplier_id
        )
        if products_with_po:
            query = query.filter(~ProductSupplier.product_id.in_(products_with_po))
        no_po_default_links = query.all()
        default_all_removed = len(no_po_default_links)
        if apply:
            for link in no_po_default_links:
                db.delete(link)

    if apply:
        db.commit()

    return {
        "mode": "APPLIED" if apply else "DRY-RUN (no writes)",
        "products_seen": products_seen,
        "created": created,
        "promoted": promoted,
        "default_removed": default_removed,
        "default_all_removed": default_all_removed,
        "default_supplier_found": default_supplier is not None,
        "samples": samples,
    }


def _print_report(report: Dict[str, Any], *, drop_default_all: bool) -> None:
    print("\n=== summary ===")
    print(f"mode:                       {report['mode']}")
    print(f"products seen (with PO):    {report['products_seen']}")
    print(f"links created:              {report['created']}")
    print(f"links promoted:             {report['promoted']}")
    print(f"DEFAULT links removed:      {report['default_removed']}")
    if drop_default_all:
        print("DEFAULT links removed (no-PO products, --drop-default-all): "
              f"{report['default_all_removed']}")
    if report["samples"]:
        print("\nsample (product_code -> supplier_code):")
        for line in report["samples"]:
            print(f"  {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes. Default is dry-run (report only).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit dry-run (also the default when --apply is absent).")
    parser.add_argument("--drop-default-all", action="store_true",
                        help="Also delete the DEFAULT link of products with NO PO history.")
    parser.add_argument("--default-supplier-code", default="DEFAULT",
                        help="supplier_code identifying the placeholder link (default: DEFAULT).")
    parser.add_argument("--company", default=None,
                        help="Company CODE to run against (default: the incumbent company).")
    args = parser.parse_args()
    apply_changes = bool(args.apply)

    # See COMPANY SCOPE in the module docstring.
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
            report = run(
                db, apply=apply_changes, drop_default_all=args.drop_default_all,
                default_supplier_code=args.default_supplier_code,
            )
            if not report["default_supplier_found"]:
                print(f"no supplier with code {args.default_supplier_code!r} in this "
                      f"company scope - nothing to remove links to (creation/promotion "
                      f"still ran).")
            _print_report(report, drop_default_all=args.drop_default_all)
            return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
