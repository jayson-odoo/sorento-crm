#!/usr/bin/env python3
"""Report existing rows that collide under `normalize_code` (D17, S1).

Ingest-parity-standardisation moves every master's adoption match from an
exact-string comparison to `upper(btrim(code))` (`app/services/rules/
master_rules.resolve_master_by_code`). Before that rule lands, a table that
already holds two rows spelling the same code differently (`"BRW"` and
`" brw "`) has both surviving side by side; once the rule is live, a push
naming either spelling adopts whichever row the match query happens to
return first - silently picking one of two existing rows rather than the
duplication the rule exists to prevent.

This script finds those collisions AHEAD of the rule landing, so they can be
reviewed and merged by hand. Print only - it never writes.

Run from sorento_crm_backend/:
    venv/bin/python scripts/report_case_variant_masters.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import engine

#: (table, code_column) for every master `resolve_master_by_code` now
#: matches through. `customers` is absent - its identity is the (code, name)
#: pair (D13), never the code alone, so a code-only collision there is not
#: the bug this rule is guarding against. `sales_agents` is absent too - it
#: already matches `upper(btrim())` (the agent master's own long-standing
#: rule, not something this slice changes).
_TABLES = [
    ("warehouses", "warehouse_code"),
    ("suppliers", "supplier_code"),
    ("product_categories", "category_code"),
    ("units_of_measure", "uom_code"),
    ("products", "product_code"),
    ("brands", "brand_code"),
]


def _collisions(table: str, column: str) -> list[dict]:
    sql = text(
        f"""
        SELECT company_id, upper(btrim({column})) AS normalized,
               array_agg(id ORDER BY id) AS ids,
               array_agg({column} ORDER BY id) AS raw_codes
        FROM {table}
        GROUP BY company_id, upper(btrim({column}))
        HAVING count(DISTINCT {column}) > 1
        ORDER BY company_id, normalized
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def main() -> int:
    total = 0
    for table, column in _TABLES:
        rows = _collisions(table, column)
        if not rows:
            print(f"{table}: no case/whitespace collisions")
            continue
        print(f"{table}: {len(rows)} collision group(s)")
        for row in rows:
            total += 1
            print(
                f"  company={row['company_id']} normalized={row['normalized']!r} "
                f"codes={row['raw_codes']} ids={row['ids']}"
            )
    print(f"\n{total} collision group(s) total across {len(_TABLES)} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
