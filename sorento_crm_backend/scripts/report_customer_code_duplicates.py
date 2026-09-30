"""Read-only report of customer rows sharing one debtor code within a company.

The blast radius of migration ``cci_0001_customer_code_identity``'s merge, shown
BEFORE it runs: per (company, code) group, every row with its name, whether it
holds an integration reference, its order counts (``orders`` + ``sales_orders``),
its contacts and Respond.io links, and which row the migration would keep. A
name that shares no word with the survivor's is flagged ``odd-name`` so the
owner can eyeball the groups where two genuinely different businesses may sit
under one code (recommendation: still merge - AutoCount is the truth for
debtors - but see them first).

    python -m scripts.report_customer_code_duplicates            # table
    python -m scripts.report_customer_code_duplicates --json     # machine-readable

Writes nothing. Reads ``DATABASE_URL`` from the environment / ``.env`` like the app.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from sqlalchemy import text

from app.database import SessionLocal

_SQL = """
WITH dup AS (
    SELECT company_id, lower(btrim(customer_code)) AS code_key
    FROM customers
    GROUP BY 1, 2
    HAVING count(*) > 1
)
SELECT
    co.name AS company,
    c.company_id,
    dup.code_key,
    c.id,
    c.customer_code,
    c.customer_name,
    c.created_at,
    (SELECT string_agg(r.source_ref, ', ') FROM integration_references r
      WHERE r.entity_type = 'customers' AND r.entity_id = c.id::text) AS refs,
    (SELECT count(*) FROM orders o WHERE o.customer_id = c.id) AS delivery_orders,
    (SELECT count(*) FROM sales_orders s WHERE s.customer_id = c.id) AS sales_orders,
    (SELECT count(*) FROM customer_contacts cc WHERE cc.customer_id = c.id) AS contacts,
    (SELECT count(*) FROM respond_contact_customers l WHERE l.customer_id = c.id) AS respond_links
FROM customers c
JOIN dup ON dup.company_id = c.company_id AND dup.code_key = lower(btrim(c.customer_code))
LEFT JOIN companies co ON co.id = c.company_id
ORDER BY co.name, dup.code_key, c.created_at, c.id
"""

_WORD = re.compile(r"[A-Za-z0-9]{3,}")
_NOISE = {"SDN", "BHD", "THE", "AND", "ENTERPRISE", "TRADING", "SUPPLY", "SUPPLIES"}


def _words(name: str) -> set[str]:
    return {w.upper() for w in _WORD.findall(name or "")} - _NOISE


def _survivor(rows: list[dict]) -> dict:
    """The row the migration keeps: ref holder, else most orders, else oldest."""
    return sorted(
        rows,
        key=lambda r: (
            0 if r["refs"] else 1,
            -(int(r["delivery_orders"]) + int(r["sales_orders"])),
            r["created_at"] or "",
            str(r["id"]),
        ),
    )[0]


def build_report(db) -> list[dict]:
    rows = [dict(r) for r in db.execute(text(_SQL)).mappings().all()]
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["company"], row["code_key"]), []).append(row)
    report: list[dict] = []
    for (company, code_key), members in groups.items():
        keep = _survivor(members)
        keep_words = _words(keep["customer_name"])
        report.append(
            {
                "company": company,
                "code": code_key,
                "rows": len(members),
                "survivor": str(keep["id"]),
                "members": [
                    {
                        "id": str(m["id"]),
                        "name": m["customer_name"],
                        "keep": m is keep,
                        "refs": m["refs"] or "",
                        "delivery_orders": int(m["delivery_orders"]),
                        "sales_orders": int(m["sales_orders"]),
                        "contacts": int(m["contacts"]),
                        "respond_links": int(m["respond_links"]),
                        "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                        "odd_name": (m is not keep) and not (_words(m["customer_name"]) & keep_words),
                    }
                    for m in members
                ],
            }
        )
    return report


def _print_table(report: list[dict]) -> None:
    total_rows = sum(g["rows"] for g in report)
    total_losers = total_rows - len(report)
    print(f"{len(report)} duplicated codes, {total_rows} rows, {total_losers} rows would be merged away")
    print()
    for group in report:
        print(f"[{group['company']}] {group['code']}  ({group['rows']} rows)")
        for m in group["members"]:
            mark = "KEEP " if m["keep"] else ("odd  " if m["odd_name"] else "merge")
            print(
                f"  {mark}  {m['name']!r:60}  refs={m['refs'] or '-':<24} "
                f"DO={m['delivery_orders']:<4} SO={m['sales_orders']:<4} "
                f"contacts={m['contacts']:<3} respond={m['respond_links']}"
            )
        print()
    odd = sum(1 for g in report for m in g["members"] if m["odd_name"])
    print(f"{odd} merged-away rows carry a name sharing no word with their survivor (odd-name)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        report = build_report(db)
    finally:
        db.rollback()
        db.close()
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
