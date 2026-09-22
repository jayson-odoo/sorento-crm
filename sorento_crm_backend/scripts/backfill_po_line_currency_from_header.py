#!/usr/bin/env python3
"""One-off: repoint a purchase-order LINE's currency at its own HEADER's currency,
for every line the old assumed-CNY fill mis-stamped - whatever feed wrote it.

`PLAN-po-line-currency-follows-header-22sep.md` (owner ruling 22 Sep 2026: "we
shouldn't assume CNY"). Before that lane's fix, an autocount push or upload with no
stated line currency wrote `DEFAULT_PO_CURRENCY` ("CNY") straight onto the line, even
when the SAME document's header carried a real currency the file (or a prior line on
it) had stated. Measured on the 0921 prod copy: 66,720 `purchase_order_lines` rows
whose currency differs from their header's, every one of them `CNY` on the line side -
66,084 autocount (USD 45,681 / MYR 20,358 / EUR 36 / SGD 9) plus 636 `scm_po_history`
rows (header USD, line CNY), the same mis-stamp from a different feed (fix round 1: the
first cut of this script scoped the UPDATE to `source_system = 'autocount'` and left
those 636 behind - the rule is about what the currency IS, not which feed wrote it).
Measured separately: zero rows anywhere have a CNY header with a non-CNY line, so this
can never demote a correct line to a wrong one. The service-level fix stops the
mis-stamp for a new push or upload; this script repairs what already landed that way.

WHAT IT DOES
------------
One UPDATE: `purchase_order_lines.currency = purchase_orders.currency` for every line
whose header carries a currency and whose own currency differs from it - any line,
regardless of `source_system`. Untouched: any line whose header carries NO currency
(stays whatever it is), and any line that already matches its header.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT and writes nothing. `--apply` runs the UPDATE and commits
once. A second `--apply` run matches and changes 0 rows - the WHERE clause is exactly
the mismatch this script exists to close.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_po_line_currency_from_header.py --dry-run
    venv/bin/python scripts/backfill_po_line_currency_from_header.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

#: Every line whose currency does not match its own header's, whatever feed wrote
#: either row, as (header_currency, line_currency, count) triples - what `--dry-run`
#: would move.
_PAIRS_SQL = text(
    """
    SELECT po.currency AS header_currency, pol.currency AS line_currency, COUNT(*) AS n
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    WHERE po.currency IS NOT NULL
      AND pol.currency IS DISTINCT FROM po.currency
    GROUP BY po.currency, pol.currency
    ORDER BY po.currency, pol.currency
    """
)

_UPDATE_SQL = text(
    """
    UPDATE purchase_order_lines AS pol
    SET currency = po.currency
    FROM purchase_orders AS po
    WHERE pol.purchase_order_id = po.id
      AND po.currency IS NOT NULL
      AND pol.currency IS DISTINCT FROM po.currency
    """
)


def _pairs(db) -> List[Tuple[Any, Any, int]]:
    return [
        (row.header_currency, row.line_currency, row.n)
        for row in db.execute(_PAIRS_SQL).all()
    ]


def run(db, *, apply: bool = False) -> Dict[str, Any]:
    """The sweep itself, under the caller's own (already active) company scope.

    Returns ``before``/``after`` (the mismatch pairs, each a
    ``(header_currency, line_currency, count)`` triple) and ``changed`` (rows
    actually written - 0 on a dry run).
    """
    before = _pairs(db)
    changed = 0
    if apply:
        result = db.execute(_UPDATE_SQL)
        changed = result.rowcount or 0
        db.commit()
    after = _pairs(db) if apply else before
    return {"before": before, "after": after, "changed": changed}


def _print_pairs(label: str, pairs: List[Tuple[Any, Any, int]]) -> None:
    print(f"{label}:")
    if not pairs:
        print("  (none)")
        return
    for header_currency, line_currency, count in pairs:
        print(f"  header {header_currency!r} / line {line_currency!r}: {count}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply", action="store_true", help="Write the changes. Default is dry-run."
    )
    mode.add_argument(
        "--dry-run", action="store_true", help="Explicit dry-run (also the default)."
    )
    args = parser.parse_args(argv)
    apply_changes = bool(args.apply)

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    try:
        # Defensive only: both `_PAIRS_SQL` and `_UPDATE_SQL` are raw `text()` and
        # never go through the ORM's company-scope filter either way, so this has no
        # effect on what the two statements above see - set anyway so any FUTURE
        # ORM-side query added to this script (there is none today) fails closed by
        # default instead of silently reading one company, the same reason
        # `backfill_order_back_rows.py` sets it.
        set_company_scope(db, None)

        print(f"mode: {'APPLY' if apply_changes else 'DRY-RUN (no writes)'}")
        report = run(db, apply=apply_changes)
        _print_pairs("before", report["before"])
        print(f"\nchanged: {report['changed']}")
        _print_pairs("after", report["after"])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
