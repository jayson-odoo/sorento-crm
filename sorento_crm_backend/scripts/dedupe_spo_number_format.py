#!/usr/bin/env python3
"""Reconcile the two spellings of an SPO number and merge the twin documents they created.

ROOT CAUSE
----------
`PLAN-spo-number-format-dedupe.md`. Two spellings of one SPO number lived side by side:
`SPO-yyyy/mm-xxxx` (the outstanding/history book upload, `source_system = scm_upload`) and
`SPO-yyyymm-xxxx` (`spo_conversion_service.create`'s CRM path, before its numbering rule was
fixed to mint the slash spelling). A third, rarer shape is a plain book-upload typo -
`SPO-20254/12-0074` where `SPO-2025/12-0074` was meant.

`outstanding_import_service._spo_line_plans` (and the equivalent header lookup for a regular
purchase order) match on the EXACT string, so `SPO-202608-0090 != SPO-2026/08-0090` and the
upload minted a second document instead of restating the first. `scm.on_order_v` reads both,
so an affected SPO counted its incoming supply twice.

WHAT IT DOES
------------
Survivor = the BOOK row (`source_system = scm_upload`, slash spelling): the upload only
restates rows it owns, so a CRM-spelled survivor would never receive the book's own receipt
figures again on a future upload. Two steps, run as ONE document at a time:

  Step A - rename a plain/typo spelling that has NO existing target spelling in the same
  table + company. Idempotent: a row already renamed, or one with no twin at all, is left
  alone on a re-run.

  Step B - merge a plain/typo spelling that DOES have an existing target (a genuine twin):
    1. Header (`purchase_orders`). The target header survives; `supplier_id`, `issue_date`,
       `expected_date`, `currency`, `source_ref` are filled from the twin where the survivor
       is NULL (a `source_ref` value on BOTH sides is a conflict - the survivor's value is
       kept, the discarded one is logged). Every FK column anywhere in the database that
       references `purchase_orders.id` is repointed from the twin's id to the survivor's,
       except `purchase_order_lines.purchase_order_id` (handled by step 2).
    2. PO lines (`purchase_order_lines`), matched to an unclaimed survivor line by
       `(product_id, qty_ordered)` then by `product_id` alone (oldest line first). A match
       repoints every FK referencing the twin line's id onto the survivor line's id, then
       deletes the twin line. No match: the line is MOVED onto the survivor header, kept
       exactly as it is. Because this step runs BEFORE step 3, an allocation's `po_line_id`
       already reads the repointed value by the time step 3 looks at it - no separate
       remap table is needed.
    3. Allocations (`spo_allocations`), matched to an unclaimed survivor allocation by
       `(product_id, warehouse_id, allocated_quantity)`, then `(product_id, warehouse_id)`,
       then `product_id` alone (lowest `spo_line_number` first). A match repoints every FK
       referencing the twin allocation's id (discovered at runtime - `picking_lines`,
       `projects.order_inquiry_links`, `scm.order_link_claim` and anything added later) onto
       the survivor's id, copies `inbound_shipment_id` / `created_by` / `allocation_notes` /
       `po_line_id` onto the survivor where it is NULL, and deletes the twin. The survivor's
       own `allocated_quantity` / `quantity_received` / `receipt_status` are never
       overwritten (the book is truth) - a difference is only logged. No match: the
       allocation is MOVED onto the survivor's number with a fresh
       `next_spo_line_number()`.

Every FK repoint is discovered at runtime from `pg_constraint`, never a hardcoded table
list - `purchase_orders.id` / `purchase_order_lines.id` / `spo_allocations.id` are each
referenced by more tables than the three the plan names by hand (`scm.plan_exception`,
`scm.shipment_line_spo_link`, `projects.order_inquiry_rows`, `scm.loading_plan_line` among
them), and a hardcoded list silently stops covering a table added after this script was
written.

`sync_received_for_spo_number` (it commits on its own) is deliberately NOT called inside the
merge transaction - every survivor number is collected and synced once, AFTER the single
commit.

DEVIATION FROM THE PLAN, MEASURED
----------------------------------
The plan describes 230 CRM-created `purchase_orders` headers under the plain SPO spelling.
Measured against the local database (a prod copy, 7 Sep 2026): `purchase_orders.po_number`
carries ZERO rows shaped like `SPO-...` today (one legacy `CRM-SPO-<hex>` row from before
doc numbering existed, which matches neither regex and is untouched by this script). Whatever
cleanup already reached the header side, Step A/B's header handling is still implemented
exactly as specified - a book-only SPO (the overwhelming majority) has no header row on
either spelling and the header step is a no-op for it, which is what actually happens today.
`purchase_order_lines` has no `line_number` column and no line-number unique key at all, so
"renumber if a line-number unique key exists" (step 2's unmatched-line move) has nothing to
renumber; the line is moved with everything else left as it is.

SAFETY / IDEMPOTENCY
---------------------
- `--dry-run` is the DEFAULT. Every write in this module is gated behind `apply=True`, so a
  dry run issues no UPDATE/DELETE/INSERT at all - only SELECTs - and still prints the exact
  per-document plan and writes the backup/preview JSON (`"dry_run": true`).
- `--apply` runs the whole thing in ONE transaction; any exception rolls it back completely
  (the caller, `main()`, catches and re-raises after `db.rollback()`).
- Before any delete's effect becomes permanent, a full backup is written to
  `scripts/out/dedupe_spo_<UTC ts>_<hex>.json`: every twin's header/line/allocation row (full
  column dump), the match table, every FK repoint (table, column, old id, new id, rows
  affected), and every value conflict logged along the way.
- `--spo <number>` (repeatable) limits the run to specific documents - either spelling, or
  the exact malformed string for the typo case (which shares no match-key with its target).
  Take a `pg_dump -t purchase_orders -t purchase_order_lines -t spo_allocations` first.

Run from sorento_crm_backend/:
    venv/bin/python scripts/dedupe_spo_number_format.py                 # dry run, everything
    venv/bin/python scripts/dedupe_spo_number_format.py --spo SPO-2025/12-0074
    venv/bin/python scripts/dedupe_spo_number_format.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.services.procurement_service import (
    PickingHeaderService,
    _spo_match_key,
    next_spo_line_number,
)

#: `purchase_orders.po_number` / `spo_allocations.spo_number` - the two columns this script
#: reconciles. `spo_allocations` is scanned second so a header-only rename (rare - see the
#: module docstring's measured deviation) never blocks on an allocation twin that has not
#: been classified yet.
TABLES: Tuple[Tuple[str, str], ...] = (
    ("purchase_orders", "po_number"),
    ("spo_allocations", "spo_number"),
)

#: `SPO-202608-0090` -> `SPO-2026/08-0090`.
_PLAIN_RE = re.compile(r"^SPO-(\d{4})(\d{2})-(\d{4})$")
#: `SPO-20254/12-0074` -> `SPO-2025/12-0074`. The stray digit is dropped, not captured -
#: it shares no `_spo_match_key` with its target, which is why this script matches on the
#: exact computed target string rather than grouping by match key.
_TYPO_RE = re.compile(r"^SPO-(\d{4})\d/(\d{2})-(\d{4})$")


def _target_spelling(raw: Optional[str]) -> Optional[str]:
    """The canonical `SPO-yyyy/mm-xxxx` spelling `raw` should carry, or None if it already
    does (or is not one of the two malformed shapes this script knows about)."""
    if not raw:
        return None
    m = _PLAIN_RE.match(raw)
    if m:
        year, month, seq = m.groups()
        return f"SPO-{year}/{month}-{seq}"
    m = _TYPO_RE.match(raw)
    if m:
        year, month, seq = m.groups()
        return f"SPO-{year}/{month}-{seq}"
    return None


def _referencing_fks(db: Session, table: str, id_column: str = "id") -> List[Tuple[str, str]]:
    """Every `(schema.table, column)` anywhere in the database with a foreign key onto
    `table.id_column`, resolved from `pg_constraint` at RUNTIME rather than a hardcoded list.

    `table` is looked up via `to_regclass()`, which resolves through the CALLER's own
    `search_path` - the real table in production, a test's scratch-schema copy under a test
    fixture that translates the default schema. The referencing side is always returned
    schema-qualified (`quote_ident`), independent of search_path, so the caller's raw SQL
    against it is correct whatever schema it actually lives in (`scm.order_link_claim`,
    `projects.order_inquiry_links`, ...).
    """
    rows = db.execute(
        text(
            """
            SELECT
                quote_ident(rn.nspname) || '.' || quote_ident(rc.relname) AS ref_table,
                ra.attname AS ref_column
            FROM pg_constraint c
            JOIN pg_class rc ON rc.oid = c.conrelid
            JOIN pg_namespace rn ON rn.oid = rc.relnamespace
            JOIN unnest(c.conkey) WITH ORDINALITY AS ck(attnum, ord) ON true
            JOIN pg_attribute ra ON ra.attrelid = c.conrelid AND ra.attnum = ck.attnum
            JOIN unnest(c.confkey) WITH ORDINALITY AS cfk(attnum, ord) ON cfk.ord = ck.ord
            JOIN pg_attribute ta ON ta.attrelid = c.confrelid AND ta.attnum = cfk.attnum
            WHERE c.contype = 'f'
              AND c.confrelid = to_regclass(:t)::oid
              AND ta.attname = :idcol
            ORDER BY 1, 2
            """
        ),
        {"t": table, "idcol": id_column},
    ).all()
    return [(r[0], r[1]) for r in rows]


def _candidates(
    db: Session, table: str, column: str, spo_filter: List[str]
) -> List[Tuple[Any, str, str]]:
    """`(company_id, raw, target)` for every distinct value in `table.column` that is one of
    the two malformed shapes. `spo_filter` (either spelling, or the exact malformed string)
    is pushed into the SQL so a surgical `--spo` run never scans rows outside its own scope -
    load-bearing on the shared dev database, which holds real production data."""
    sql = f"SELECT DISTINCT company_id, {column} FROM {table} WHERE {column} LIKE 'SPO-%'"
    params: Dict[str, Any] = {}
    if spo_filter:
        sql += (
            f" AND ({column} = ANY(:raw) OR "
            f"upper(regexp_replace({column}, '[^A-Za-z0-9]', '', 'g')) = ANY(:keys))"
        )
        params["raw"] = list(spo_filter)
        params["keys"] = [_spo_match_key(v) for v in spo_filter]
    rows = db.execute(text(sql), params).all()
    out: List[Tuple[Any, str, str]] = []
    for company_id, raw in rows:
        target = _target_spelling(raw)
        if target and target != raw:
            out.append((company_id, raw, target))
    return out


def _exists_value(db: Session, table: str, column: str, company_id: Any, value: str) -> bool:
    row = db.execute(
        text(f"SELECT 1 FROM {table} WHERE company_id = :c AND {column} = :v LIMIT 1"),
        {"c": company_id, "v": value},
    ).first()
    return row is not None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {c.name: _jsonable(getattr(row, c.name)) for c in row.__table__.columns}


def _repoint(
    db: Session,
    apply: bool,
    ref_table: str,
    ref_col: str,
    old_id: Any,
    new_id: Any,
    log: List[Dict[str, Any]],
) -> int:
    """Repoint one FK column, or (dry run) report how many rows it would touch."""
    if apply:
        n = db.execute(
            text(f"UPDATE {ref_table} SET {ref_col} = :new WHERE {ref_col} = :old"),
            {"new": new_id, "old": old_id},
        ).rowcount
    else:
        n = db.execute(
            text(f"SELECT count(*) FROM {ref_table} WHERE {ref_col} = :old"), {"old": old_id}
        ).scalar()
    if n:
        log.append(
            {
                "table": ref_table,
                "column": ref_col,
                "old": str(old_id),
                "new": str(new_id),
                "rows": n,
            }
        )
    return n


_HEADER_FILL_COLS = ("supplier_id", "issue_date", "expected_date", "currency", "source_ref")


def _merge_header(
    db: Session,
    apply: bool,
    company_id: Any,
    target: str,
    old_list: List[str],
    doc_backup: Dict[str, Any],
) -> None:
    """Step 1 (+2, nested): merge every `purchase_orders` row under `old_list` into the row
    named `target`, or - when `target` has no header at all - rename the twin in place
    (the same rule Step A applies, for a header-only twin that Step A itself never saw)."""
    s_header = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.company_id == company_id, PurchaseOrder.po_number == target)
        .one_or_none()
    )
    p_headers = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.company_id == company_id, PurchaseOrder.po_number.in_(old_list))
        .all()
    )
    if not p_headers:
        return

    if s_header is None:
        for p in p_headers:
            doc_backup.setdefault("header_renames", []).append(
                {"id": str(p.id), "old": p.po_number, "new": target}
            )
            print(f"  [header] {p.po_number} has no header twin - renaming to {target}")
            if apply:
                p.po_number = target
        if apply:
            db.flush()
        return

    fk_list = [
        fk
        for fk in _referencing_fks(db, "purchase_orders")
        if not (fk[0].rsplit(".", 1)[-1] == "purchase_order_lines" and fk[1] == "purchase_order_id")
    ]

    for p in p_headers:
        print(f"  [header] merging {p.po_number} ({p.id}) into {target} ({s_header.id})")
        doc_backup.setdefault("headers", []).append(_row_to_dict(p))

        for col in _HEADER_FILL_COLS:
            p_val = getattr(p, col)
            if p_val is None:
                continue
            s_val = getattr(s_header, col)
            if s_val is None:
                doc_backup.setdefault("header_fills", []).append(
                    {"column": col, "from_id": str(p.id), "to_id": str(s_header.id),
                     "value": _jsonable(p_val)}
                )
                if apply:
                    setattr(s_header, col, p_val)
            elif col == "source_ref" and str(s_val) != str(p_val):
                doc_backup.setdefault("header_conflicts", []).append(
                    {"column": col, "kept": _jsonable(s_val), "discarded": _jsonable(p_val),
                     "discarded_from_id": str(p.id)}
                )
        if apply:
            db.flush()

        for ref_table, ref_col in fk_list:
            _repoint(db, apply, ref_table, ref_col, p.id, s_header.id,
                     doc_backup.setdefault("fk_repoints", []))

        _merge_po_lines(db, apply, p.id, s_header.id, doc_backup)

        doc_backup.setdefault("deleted", []).append({"table": "purchase_orders", "id": str(p.id)})
        if apply:
            db.delete(p)
            db.flush()


def _merge_po_lines(
    db: Session, apply: bool, p_header_id: Any, s_header_id: Any, doc_backup: Dict[str, Any]
) -> None:
    """Step 2: match `purchase_order_lines` under the twin header onto unclaimed lines of the
    survivor header, oldest first. A match repoints every FK onto the twin line before it is
    deleted; an unmatched line is MOVED (`purchase_order_lines` has no line-number column or
    unique key to renumber - see the module docstring)."""
    s_lines = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == s_header_id)
        .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
        .all()
    )
    p_lines = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == p_header_id)
        .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
        .all()
    )
    if not p_lines:
        return

    unclaimed = list(s_lines)
    matched: List[Tuple[PurchaseOrderLine, PurchaseOrderLine]] = []

    def _pass(predicate, remaining):
        leftover = []
        for p in remaining:
            hit = next((s for s in unclaimed if predicate(p, s)), None)
            if hit is not None:
                unclaimed.remove(hit)
                matched.append((p, hit))
            else:
                leftover.append(p)
        return leftover

    remaining = _pass(
        lambda p, s: s.product_id == p.product_id and s.qty_ordered == p.qty_ordered, p_lines
    )
    remaining = _pass(lambda p, s: s.product_id == p.product_id, remaining)

    fk_list = _referencing_fks(db, "purchase_order_lines")
    for p, s in matched:
        doc_backup.setdefault("po_lines", []).append(_row_to_dict(p))
        for ref_table, ref_col in fk_list:
            _repoint(db, apply, ref_table, ref_col, p.id, s.id,
                     doc_backup.setdefault("fk_repoints", []))
        doc_backup.setdefault("deleted", []).append(
            {"table": "purchase_order_lines", "id": str(p.id)}
        )
        if apply:
            db.delete(p)

    for p in remaining:
        doc_backup.setdefault("po_lines_moved", []).append(
            {"id": str(p.id), "from_header": str(p_header_id), "to_header": str(s_header_id)}
        )
        if apply:
            p.purchase_order_id = s_header_id

    if apply:
        db.flush()


_ALLOC_FILL_COLS = ("inbound_shipment_id", "created_by", "allocation_notes", "po_line_id")
_ALLOC_BOOK_TRUTH_COLS = ("allocated_quantity", "quantity_received", "receipt_status")


def _merge_allocations(
    db: Session,
    apply: bool,
    company_id: Any,
    target: str,
    old_list: List[str],
    doc_backup: Dict[str, Any],
    counters: Dict[str, int],
) -> None:
    """Step 3: match `spo_allocations` under the twin number onto unclaimed allocations of
    the survivor number, lowest `spo_line_number` first. A matched twin fills the survivor's
    NULL columns (never overwrites - the book's own figures are truth, a difference is only
    logged) and is deleted; an unmatched twin is MOVED onto the survivor number with a fresh
    line number."""
    s_allocs = (
        db.query(SPOAllocation)
        .filter(SPOAllocation.company_id == company_id, SPOAllocation.spo_number == target)
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )
    p_allocs = (
        db.query(SPOAllocation)
        .filter(SPOAllocation.company_id == company_id, SPOAllocation.spo_number.in_(old_list))
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )
    if not p_allocs:
        return

    unclaimed = list(s_allocs)
    matched: List[Tuple[SPOAllocation, SPOAllocation]] = []

    def _pass(predicate, remaining):
        leftover = []
        for p in remaining:
            hit = next((s for s in unclaimed if predicate(p, s)), None)
            if hit is not None:
                unclaimed.remove(hit)
                matched.append((p, hit))
            else:
                leftover.append(p)
        return leftover

    remaining = _pass(
        lambda p, s: (s.product_id, s.warehouse_id, s.allocated_quantity)
        == (p.product_id, p.warehouse_id, p.allocated_quantity),
        p_allocs,
    )
    remaining = _pass(
        lambda p, s: (s.product_id, s.warehouse_id) == (p.product_id, p.warehouse_id), remaining
    )
    remaining = _pass(lambda p, s: s.product_id == p.product_id, remaining)

    fk_list = _referencing_fks(db, "spo_allocations")
    for p, s in matched:
        doc_backup.setdefault("allocations", []).append(_row_to_dict(p))
        for col in _ALLOC_FILL_COLS:
            p_val = getattr(p, col)
            if p_val is None:
                continue
            if getattr(s, col) is None:
                doc_backup.setdefault("alloc_fills", []).append(
                    {"column": col, "from_id": str(p.id), "to_id": str(s.id),
                     "value": _jsonable(p_val)}
                )
                if apply:
                    setattr(s, col, p_val)
        for col in _ALLOC_BOOK_TRUTH_COLS:
            if getattr(s, col) != getattr(p, col):
                doc_backup.setdefault("alloc_value_conflicts", []).append(
                    {"column": col, "kept": _jsonable(getattr(s, col)),
                     "discarded": _jsonable(getattr(p, col)), "s_id": str(s.id), "p_id": str(p.id)}
                )
        if apply:
            db.flush()

        for ref_table, ref_col in fk_list:
            _repoint(db, apply, ref_table, ref_col, p.id, s.id,
                     doc_backup.setdefault("fk_repoints", []))
        doc_backup.setdefault("deleted", []).append({"table": "spo_allocations", "id": str(p.id)})
        if apply:
            db.delete(p)

    for p in remaining:
        new_line_number = next_spo_line_number(db, target, taken=counters)
        doc_backup.setdefault("allocations_moved", []).append(
            {"id": str(p.id), "old_spo_number": p.spo_number, "new_spo_number": target,
             "new_spo_line_number": new_line_number}
        )
        if apply:
            p.spo_number = target
            p.spo_line_number = new_line_number

    if apply:
        db.flush()


def _verify_before_commit(db: Session, backup: Dict[str, Any]) -> None:
    """Step 5. Raising here (before `main()` commits) rolls the whole run back.

    Both checks are scoped to what THIS RUN actually touched (every rename's old/new,
    every merge's target and old spellings) rather than the whole table: a `--spo`
    surgical run - and every test in this suite - leaves the rest of a shared, real
    database exactly as it found it, malformed rows included, and a global scan would
    both be slow against it and fail on pre-existing data this run was never asked to
    fix. An unfiltered run still gets full coverage: `_candidates` already found every
    malformed row in the table, so "touched" already covers all of them.
    """
    deleted: Dict[str, set] = {}
    touched: set = set()
    for rename in backup.get("renames", []):
        touched.add(rename["old"])
        touched.add(rename["new"])
    for entry in backup.get("merges", []):
        touched.add(entry["target"])
        touched.update(entry.get("old_spellings", []))
        for d in entry.get("deleted", []):
            deleted.setdefault(d["table"], set()).add(d["id"])

    for table, ids in deleted.items():
        if not ids:
            continue
        for ref_table, ref_col in _referencing_fks(db, table):
            rows = db.execute(
                text(f"SELECT {ref_col} FROM {ref_table} WHERE {ref_col}::text = ANY(:ids)"),
                {"ids": list(ids)},
            ).fetchall()
            if rows:
                raise RuntimeError(
                    f"verification failed: {ref_table}.{ref_col} still references a deleted "
                    f"{table} id: {[str(r[0]) for r in rows]}"
                )

    if touched:
        for table, column in TABLES:
            n = db.execute(
                text(
                    f"SELECT count(*) FROM {table} WHERE {column} = ANY(:touched) "
                    f"AND ({column} ~ :plain OR {column} ~ :typo)"
                ),
                {"touched": list(touched), "plain": _PLAIN_RE.pattern, "typo": _TYPO_RE.pattern},
            ).scalar()
            if n:
                raise RuntimeError(
                    f"verification failed: {n} row(s) in {table}.{column} still malformed"
                )

    if touched:
        dupes = db.execute(
            text(
                "SELECT company_id, spo_number, spo_line_number, count(*) FROM spo_allocations "
                "WHERE spo_number = ANY(:touched) GROUP BY 1, 2, 3 HAVING count(*) > 1"
            ),
            {"touched": list(touched)},
        ).fetchall()
        if dupes:
            raise RuntimeError(
                f"verification failed: duplicate (company, spo_number, spo_line_number): {dupes}"
            )


def _write_backup(backup: Dict[str, Any]) -> Path:
    out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"dedupe_spo_{ts}_{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(backup, indent=2, default=_jsonable))
    return path


def run(db: Session, *, apply: bool, spo_filter: Optional[List[str]] = None) -> Dict[str, Any]:
    """Report (and, with `apply=True`, perform) every rename and merge. The caller commits -
    this never calls `db.commit()` or `db.rollback()` itself, so a test can wrap the call in
    its own savepoint and a forced mid-run failure rolls back cleanly."""
    spo_filter = spo_filter or []
    backup: Dict[str, Any] = {"dry_run": not apply, "renames": [], "merges": []}
    counters: Dict[str, int] = {}

    step_a: List[Tuple[str, str, Any, str, str]] = []
    step_b: Dict[Tuple[Any, str], set] = {}
    for table, column in TABLES:
        for company_id, old, target in _candidates(db, table, column, spo_filter):
            if _exists_value(db, table, column, company_id, target):
                step_b.setdefault((company_id, target), set()).add(old)
            else:
                step_a.append((table, column, company_id, old, target))

    for table, column, company_id, old, target in step_a:
        print(f"[rename] {table}.{column}: {old} -> {target} (company {company_id})")
        if apply:
            n = db.execute(
                text(
                    f"UPDATE {table} SET {column} = :new "
                    f"WHERE company_id = :c AND {column} = :old"
                ),
                {"new": target, "c": company_id, "old": old},
            ).rowcount
        else:
            n = db.execute(
                text(f"SELECT count(*) FROM {table} WHERE company_id = :c AND {column} = :old"),
                {"c": company_id, "old": old},
            ).scalar()
        backup["renames"].append(
            {"table": table, "column": column, "company_id": str(company_id),
             "old": old, "new": target, "rows": n}
        )
    if apply and step_a:
        db.flush()

    survivor_numbers: set = set()
    for (company_id, target), old_spellings in sorted(
        step_b.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
    ):
        old_list = sorted(old_spellings)
        print(f"[merge] {target} (company {company_id}) <- {old_list}")
        doc_backup: Dict[str, Any] = {
            "company_id": str(company_id), "target": target, "old_spellings": old_list,
        }
        _merge_header(db, apply, company_id, target, old_list, doc_backup)
        _merge_allocations(db, apply, company_id, target, old_list, doc_backup, counters)
        backup["merges"].append(doc_backup)
        survivor_numbers.add(target)

    if apply:
        _verify_before_commit(db, backup)

    backup_path = _write_backup(backup)

    return {
        "renamed": len(step_a),
        "merged_docs": len(step_b),
        "survivor_numbers": sorted(survivor_numbers),
        "backup_path": str(backup_path),
        "backup": backup,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only, write nothing (the default; accepted so a run can say so out loud).",
    )
    parser.add_argument("--apply", action="store_true", help="Write the renames and merges.")
    parser.add_argument(
        "--spo", action="append", default=[],
        help="Limit to this SPO number (repeatable). Either spelling; for the rare typo "
             "shape, the exact malformed string.",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    if apply:
        print("REMINDER: take a backup first -")
        print(
            "  pg_dump -t purchase_orders -t purchase_order_lines -t spo_allocations "
            "<db> > spo_dedupe_backup.sql\n"
        )

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET (fail
    # closed, zero rows). `None` is the sanctioned system / all-companies scope.
    set_company_scope(db, None)
    try:
        result = run(db, apply=apply, spo_filter=args.spo)
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n=== summary ===")
    print(f"mode:              {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
    print(f"renamed (no twin): {result['renamed']}")
    print(f"merged documents:  {result['merged_docs']}")
    print(f"backup file:       {result['backup_path']}")

    if apply and result["survivor_numbers"]:
        sync_db = SessionLocal()
        set_company_scope(sync_db, None)
        try:
            proc = PickingHeaderService(sync_db)
            for number in result["survivor_numbers"]:
                proc.sync_received_for_spo_number(number)
        finally:
            sync_db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
