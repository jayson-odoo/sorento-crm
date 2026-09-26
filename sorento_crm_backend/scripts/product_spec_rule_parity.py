#!/usr/bin/env python3
"""Golden parity for lane #1286 (AC-S1.4): what the new rule engine changes, per product.

The stored specifications ARE the old engine's output: every derived value on the dev copy
was written by the matcher this lane replaces. So parity is a read-only comparison of each
active product's stored DERIVED values with what `derive()` reads now, with the configured
rules as they stand after the S1 migration. A value a person set (an authored source) is not
derived and is skipped, exactly as the preview does.

Run after `alembic upgrade head` and BEFORE any catalogue re-read (a re-read overwrites the
old values this compares against):

    venv/bin/python -m scripts.product_spec_rule_parity

Writes nothing. Prints one line per changed (product, key) with before, after and the words
the new engine read, then a count per key.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_parity(db) -> Counter:
    from app.models.base import company_scope
    from app.models.product import Product, ProductCategory
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
        derive,
    )
    from app.services.product_spec_write import AUTHORED_SOURCES

    rules_by_key = configured_rules(db)
    scopes_by_key = configured_scopes(db)
    max_values = configured_max_values(db)
    per_key: Counter = Counter()
    seen: set[str] = set()

    with company_scope(db, None):
        query = (
            db.query(Product, ProductCategory, ProductSpecifications)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .order_by(Product.product_code, Product.id)
        )
        for product, category, spec in query.yield_per(500):
            if product.product_code in seen:
                continue
            seen.add(product.product_code)
            result = derive(
                product,
                category,
                rules_by_key=rules_by_key,
                scopes_by_key=scopes_by_key,
                max_values=max_values,
            )
            stored = spec.values or {}
            provenance = spec.provenance or {}
            keys = (set(stored) | set(result.values)) - {"brand"}
            for key in sorted(keys):
                if (provenance.get(key) or {}).get("source") in AUTHORED_SOURCES:
                    continue
                before = (stored.get(key) or {}).get("value")
                after = (result.values.get(key) or {}).get("value")
                if before == after:
                    continue
                per_key[key] += 1
                read = (result.provenance.get(key) or {}).get("evidence") or ""
                print(
                    f"  {product.product_code} | {key} | {before!r} -> {after!r} | "
                    f"read {read!r} | {(product.description or '')[:80]}"
                )
    print("\n  Changed per specification:")
    for key, count in per_key.most_common():
        print(f"  {key}: {count}")
    print(f"  ({sum(per_key.values())} changed values over {len(seen)} codes)")
    return per_key


def main() -> None:
    from app.database import SessionLocal

    with SessionLocal() as db:
        print_parity(db)
        db.rollback()


if __name__ == "__main__":
    main()
