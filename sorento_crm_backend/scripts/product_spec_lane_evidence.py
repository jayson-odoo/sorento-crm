#!/usr/bin/env python3
"""Read-only evidence for lane #1286 (product specifications for non-technical staff).

Prints what the S0 migration clears (the Brand specification) and what the S1 migration
converts (stored rules without a builder), so the owner sees both once before merge.
Sections match `documentation/plans/products/evidence-product-specs-non-technical.md`.

Run from sorento_crm_backend/ against the dev copy (it writes nothing):

    venv/bin/python -m scripts.product_spec_lane_evidence

The parity diff (section 6) is `scripts.product_spec_rule_parity`, run AFTER the migrations.

Run it BEFORE `alembic upgrade head`: after the migrations the rows it reports are gone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

# The sources the S0 migration treats as set by a person (`spec_0001_drop_brand._AUTHORED`),
# so section 2 lists exactly the Brand values the migration clears as hand-set.
HAND_SET_SOURCES = ("human", "supplier", "flyer")

_SECTIONS: list[tuple[str, str]] = [
    (
        "1. The brand registry row, verbatim",
        """
        SELECT is_active, rank_weight, value_weights, user_values, value_labels,
               suppressed_values, user_synonyms, excluded_values, derivation_rules
        FROM product_spec_registry WHERE spec_key = 'brand'
        """,
    ),
    (
        "1b. Other specifications' rules and scopes that name brand (they stop applying)",
        """
        SELECT spec_key, 'rule ' || ord AS what, r::text AS detail
        FROM product_spec_registry,
             jsonb_array_elements(COALESCE(derivation_rules, '[]'::jsonb))
                 WITH ORDINALITY AS t(r, ord)
        WHERE spec_key <> 'brand' AND (
              r->'applies_when' ? 'brand' OR r->'unless' ? 'brand'
              OR lower(r->'builder'->'only_when'->>'spec') = 'brand')
        UNION ALL
        SELECT spec_key, 'scope', applies_when::text
        FROM product_spec_registry
        WHERE spec_key <> 'brand' AND applies_when ? 'brand'
        ORDER BY 1, 2
        """,
    ),
    (
        "1c. Customer and segment visibility policies naming brand (spec_0003 removes it)",
        """
        SELECT id, contact_id, segment_code, spec_keys, excluded_spec_keys
        FROM spec_visibility_policies
        WHERE 'brand' = ANY(COALESCE(spec_keys, '{}'))
           OR 'brand' = ANY(COALESCE(excluded_spec_keys, '{}'))
        ORDER BY segment_code, contact_id
        """,
    ),
    (
        "2. Products whose Brand spec was set by hand",
        """
        SELECT p.product_code, s.values->'brand'->>'value' AS typed,
               s.provenance->'brand'->>'source' AS source, b.brand_name AS product_brand
        FROM product_specifications s
        JOIN products p ON p.id = s.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE s.provenance->'brand'->>'source' IN ('human', 'supplier', 'flyer')
        ORDER BY p.product_code
        """,
    ),
    (
        "3a. Stored Brand spec different from the brand field, by source",
        """
        SELECT s.provenance->'brand'->>'source' AS source, count(*) AS products
        FROM product_specifications s
        JOIN products p ON p.id = s.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE s.values ? 'brand'
          AND (b.brand_name IS NULL OR lower(b.brand_name) <> lower(s.values->'brand'->>'value'))
        GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "3b. The products behind 3a",
        """
        SELECT p.product_code, s.values->'brand'->>'value' AS spec_brand,
               b.brand_name AS product_brand, s.provenance->'brand'->>'source' AS source
        FROM product_specifications s
        JOIN products p ON p.id = s.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE s.values ? 'brand'
          AND (b.brand_name IS NULL OR lower(b.brand_name) <> lower(s.values->'brand'->>'value'))
        ORDER BY (b.brand_name IS NULL) DESC, p.product_code
        """,
    ),
    (
        "4. Company copies that disagree on brand",
        """
        SELECT p.product_code, string_agg(DISTINCT b.brand_name, ', ') AS brands
        FROM products p JOIN brands b ON b.id = p.brand_id
        GROUP BY p.product_code HAVING count(DISTINCT b.brand_name) > 1
        ORDER BY p.product_code
        """,
    ),
    (
        "5. Stored rules per specification (what S1 converts)",
        """
        SELECT spec_key, count(*) AS rules,
               count(*) FILTER (WHERE r ? 'builder') AS with_builder,
               count(*) FILTER (
                   WHERE r->>'match' IN ('regex', 'present') AND NOT (r ? '_seed')
               ) AS typed_patterns
        FROM product_spec_registry,
             jsonb_array_elements(COALESCE(derivation_rules, '[]'::jsonb)) r
        GROUP BY spec_key ORDER BY spec_key
        """,
    ),
]


def _print_rows(db, sql: str) -> None:
    result = db.execute(text(sql))
    columns = list(result.keys())
    rows = result.fetchall()
    if not rows:
        print("  (none)")
        return
    print("  " + " | ".join(columns))
    for row in rows:
        print("  " + " | ".join(json.dumps(v, default=str) if not isinstance(v, str) else v
                                for v in row))
    print(f"  ({len(rows)} rows)")


def _unconvertible(db) -> None:
    """Stored rules the S1 migration would stop on, printed before it runs."""
    from app.services.product_spec_rules import legacy_to_builder

    print("\n5b. Stored rules the S1 conversion cannot convert")
    found = 0
    for spec_key, rules in db.execute(
        text("SELECT spec_key, derivation_rules FROM product_spec_registry ORDER BY spec_key")
    ):
        for index, rule in enumerate(rules or [], start=1):
            if isinstance(rule, dict) and set(rule) <= {"builder", "_seed"}:
                continue
            if spec_key == "brand":
                continue
            if legacy_to_builder(rule, spec_key=spec_key) is None:
                found += 1
                print(f"  {spec_key} rule {index}: {json.dumps(rule)}")
    print(f"  ({found} rules)")


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    with SessionLocal() as db:
        for title, sql in _SECTIONS:
            print(f"\n{title}")
            _print_rows(db, sql)
        _unconvertible(db)
        db.rollback()


if __name__ == "__main__":
    main()
