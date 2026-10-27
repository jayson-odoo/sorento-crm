#!/usr/bin/env python3
"""Put back the AutoCount PO / SO lines the ingest hard-deleted, as Cancelled
(AC-REMOVED-KEEP-CANCELLED, owner ruling 27 Oct 2026: "it stays cancelled, but the
linkage is gone").

WHY
---
Before the fix `DocumentIngestService._sync_lines` deleted any line a push no longer
carried when nothing pointed at it. `release_removed_autocount_lines --apply` (27 Oct
11:45) released the links of 97 removed PO lines, so the next push of each PO found them
unreferenced and deleted them. Every removal since then does the same on its 2nd push.

WHAT IT DOES
------------
Reads a SNAPSHOT database holding `purchase_order_lines` and `sales_order_lines` as they
were before the deletion (a scratch DB restored from a pre-27-Oct-11:45 deploy dump), and
compares it with the live database (`DATABASE_URL`). A snapshot line is restored when ALL
of these hold:

- it carries an AutoCount `source_ref` (a DtlKey),
- its id is not in the live table,
- its document (header id) still exists live,
- no live line of that document carries the same `source_ref` (the line is still gone
  from AutoCount's push, not re-created under a new id),
- its product still exists live (a line cannot be inserted without one; reported under
  `skipped` otherwise).

The row is inserted with its original id and every column the snapshot holds, except
`line_status` = `cancelled`, `updated_at` = now and `removed_unreferenced` = true (it was
deleted, so it counted in no total; `--apply` refuses to run before migration akc_0001).
Its warehouse is set NULL when that warehouse is gone. No order inquiry link, claim or allocation is recreated: the linkage
stays gone, which is the ruling.

A second run finds nothing: every restored id is live.

SAFETY
------
Dry run by default: prints the per-document list (document no, DtlKey, product, qty
ordered / received, status in the snapshot) and writes nothing. `--apply` inserts and
commits once at the end. The snapshot DB is only read. No customer is named in the output.

USAGE
-----
    venv/bin/python -m scripts.restore_deleted_removed_lines --snapshot-db <scratch db> \
        [--company <id>]          # dry run
    ... --apply                   # write (one commit)

`--snapshot-db` reuses DATABASE_URL's host and credentials with the scratch DB's name;
`--snapshot-url` takes a full URL instead.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

logger = logging.getLogger("scripts.restore_deleted_removed_lines")

CANCELLED = "cancelled"
# Set on every restored line: it was deleted, so it counts in no total (akc_0001).
MARK = "removed_unreferenced"


@dataclass(frozen=True)
class Kind:
    line_table: str
    header_table: str
    header_fk: str
    number_column: str


KINDS = (
    Kind("purchase_order_lines", "purchase_orders", "purchase_order_id", "po_number"),
    Kind("sales_order_lines", "sales_orders", "sales_order_id", "so_number"),
)


def _dtl_key(source_ref: Optional[str]) -> str:
    """The DtlKey is the last segment of `<db>:<doc key>:<dtl key>`."""
    return (source_ref or "").rsplit(":", 1)[-1]


def _qty(value: Any) -> str:
    return format(Decimal(value or 0).normalize(), "f")


def _columns(conn: Connection, table: str) -> list[str]:
    """Columns of `table` as the current search_path resolves it (never `projects.`)."""
    rows = conn.execute(
        text(
            "SELECT a.attname FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY a.attnum"
        ),
        {"t": table},
    ).fetchall()
    return [r[0] for r in rows]


def _existing(conn: Connection, sql: str, ids: Sequence[str]) -> set:
    if not ids:
        return set()
    return {tuple(r) if len(r) > 1 else r[0] for r in conn.execute(text(sql), {"ids": list(ids)})}


def find_candidates(
    snapshot: Connection, live: Connection, kind: Kind, company_id: Optional[str]
) -> tuple[list[dict], list[dict]]:
    """(rows to restore, rows skipped with a reason). Reads only."""
    where = "source_ref IS NOT NULL"
    params: dict[str, Any] = {}
    if company_id:
        where += " AND company_id::text = :company"
        params["company"] = company_id
    snap_rows = [
        dict(r)
        for r in snapshot.execute(
            text(f"SELECT * FROM {kind.line_table} WHERE {where}"), params
        ).mappings()
    ]
    if not snap_rows:
        return [], []

    ids = [str(r["id"]) for r in snap_rows]
    header_ids = sorted({str(r[kind.header_fk]) for r in snap_rows})
    live_ids = _existing(
        live, f"SELECT id::text FROM {kind.line_table} WHERE id::text = ANY(:ids)", ids
    )
    headers = {
        str(r[0]): r[1]
        for r in live.execute(
            text(
                f"SELECT id::text, {kind.number_column} FROM {kind.header_table} "
                "WHERE id::text = ANY(:ids)"
            ),
            {"ids": header_ids},
        )
    }
    live_refs = _existing(
        live,
        f"SELECT {kind.header_fk}::text, source_ref FROM {kind.line_table} "
        f"WHERE {kind.header_fk}::text = ANY(:ids) AND source_ref IS NOT NULL",
        header_ids,
    )

    gone = [
        r
        for r in snap_rows
        if str(r["id"]) not in live_ids
        and str(r[kind.header_fk]) in headers
        and (str(r[kind.header_fk]), r["source_ref"]) not in live_refs
    ]
    products = {
        str(r[0]): r[1]
        for r in live.execute(
            text("SELECT id::text, product_code FROM products WHERE id::text = ANY(:ids)"),
            {"ids": sorted({str(r["product_id"]) for r in gone})},
        )
    }
    warehouses = _existing(
        live,
        "SELECT id::text FROM warehouses WHERE id::text = ANY(:ids)",
        sorted({str(r["warehouse_id"]) for r in gone if r.get("warehouse_id")}),
    )

    restore, skipped = [], []
    for r in gone:
        entry = {
            "row": r,
            "document": headers[str(r[kind.header_fk])],
            "dtl_key": _dtl_key(r["source_ref"]),
            "product": products.get(str(r["product_id"])),
        }
        if entry["product"] is None:
            entry["reason"] = "product no longer exists"
            skipped.append(entry)
            continue
        if r.get("warehouse_id") and str(r["warehouse_id"]) not in warehouses:
            r["warehouse_id"] = None
        restore.append(entry)
    restore.sort(key=lambda e: (e["document"], e["dtl_key"]))
    return restore, skipped


def insert_cancelled(live: Connection, kind: Kind, entries: list[dict], snapshot_cols: list[str]) -> int:
    live_cols = set(_columns(live, kind.line_table))
    if MARK not in live_cols:
        # A restored line was deleted, so it counted in no total; without the mark it would
        # start counting (owner via crew, 27 Oct). Deploy akc_0001 first.
        raise RuntimeError(f"{kind.line_table}.{MARK} is missing: deploy migration akc_0001 first")
    cols = [c for c in snapshot_cols if c in live_cols]
    fixed = ("line_status", "updated_at", MARK)
    names = [c for c in cols if c not in fixed]
    sql = text(
        f"INSERT INTO {kind.line_table} ({', '.join(names + list(fixed))}) "
        f"VALUES ({', '.join(':' + n for n in names)}, :line_status, now(), true)"
    )
    for entry in entries:
        params = {n: entry["row"].get(n) for n in names}
        params["line_status"] = CANCELLED
        live.execute(sql, params)
    return len(entries)


def _print_report(kind: Kind, restore: list[dict], skipped: list[dict]) -> None:
    print(f"== {kind.line_table}: {len(restore)} to restore, {len(skipped)} skipped")
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for e in restore:
        by_doc[e["document"]].append(e)
    for doc in sorted(by_doc):
        print(f"  {doc}")
        for e in by_doc[doc]:
            r = e["row"]
            print(
                f"    DtlKey={e['dtl_key']} product={e['product']} "
                f"qty_ordered={_qty(r.get('qty_ordered'))} "
                f"received_or_delivered={_qty(r.get('qty_received', r.get('qty_delivered')))} "
                f"snapshot_status={r.get('line_status')}"
            )
    for e in skipped:
        print(f"  SKIPPED {e['document']} DtlKey={e['dtl_key']}: {e['reason']}")


def restore(
    snapshot: Connection,
    live: Connection,
    *,
    company_id: Optional[str] = None,
    apply: bool = False,
) -> dict[str, int]:
    """Report, and with `apply` insert, every restorable line. Never commits: the caller
    owns the live transaction. Returns `{line table: rows restored (or that would be)}`."""
    out: dict[str, int] = {}
    for kind in KINDS:
        snapshot_cols = _columns(snapshot, kind.line_table)
        if not snapshot_cols:
            print(f"== {kind.line_table}: not in the snapshot DB, skipped")
            out[kind.line_table] = 0
            continue
        entries, skipped = find_candidates(snapshot, live, kind, company_id)
        _print_report(kind, entries, skipped)
        if apply and entries:
            insert_cancelled(live, kind, entries, snapshot_cols)
            print(f"   restored {len(entries)} as {CANCELLED}")
        out[kind.line_table] = len(entries)
    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply to restore.")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--snapshot-db",
        help="name of the scratch DB on the SAME server as DATABASE_URL, restored from the dump",
    )
    source.add_argument("--snapshot-url", help="full URL of the scratch DB instead")
    parser.add_argument("--company", default=None, help="limit to one company id")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    from sqlalchemy.engine import make_url

    from app.config import settings

    live_url = make_url(settings.database_url)
    snapshot_url = (
        make_url(args.snapshot_url) if args.snapshot_url else live_url.set(database=args.snapshot_db)
    )
    if snapshot_url.database == live_url.database and snapshot_url.host == live_url.host:
        parser.error("the snapshot DB is the live DB; restore the dump into a scratch DB")

    snapshot_engine = create_engine(snapshot_url)
    live_engine = create_engine(live_url)
    try:
        with snapshot_engine.connect() as snapshot, live_engine.connect() as live:
            restore(snapshot, live, company_id=args.company, apply=args.apply)
            if args.apply:
                live.commit()
            else:
                live.rollback()
    finally:
        snapshot_engine.dispose()
        live_engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
