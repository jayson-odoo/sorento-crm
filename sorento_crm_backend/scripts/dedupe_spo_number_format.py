#!/usr/bin/env python3
"""Reconcile the two spellings of an SPO number and merge the twin documents they created.

ROOT CAUSE
----------
`PLAN-spo-number-format-dedupe.md`. Two spellings of one SPO number lived side by side:
`SPO-yyyy/mm-xxxx` (the outstanding/history book upload, `source_system = scm_upload`) and
`SPO-yyyymm-xxxx` (`spo_conversion_service.create`'s CRM path, before its numbering rule was
fixed to mint the slash spelling). A third, rarer shape is a plain book-upload typo -
`SPO-20254/12-0074`, where the stray digit means the whole YEAR was mistyped, not just the
separator (see TYPO SHAPE below).

`outstanding_import_service._spo_line_plans` (and the equivalent header lookup for a regular
purchase order) match on the EXACT string, so `SPO-202608-0090 != SPO-2026/08-0090` and the
upload minted a second document instead of restating the first. `scm.on_order_v` reads both,
so an affected SPO counted its incoming supply twice.

WHAT IT DOES
------------
Survivor = the BOOK row (`source_system = scm_upload`, slash spelling): the upload only
restates rows it owns, so a CRM-spelled survivor would never receive the book's own receipt
figures again on a future upload. Two independent passes:

  Step A - rename a plain spelling that has NO existing target spelling in the same table +
  company. Idempotent: a row already renamed, or one with no twin at all, is left alone on a
  re-run. Two spellings that both target the same currently-absent number is a real (if rare)
  possibility, so a rename re-checks the target is STILL absent immediately before writing -
  not only at classification time - and reports (never crashes on the unique constraint) when
  a sibling rename in this same run got there first.

  TYPO SHAPE (rename-only, never merged): `SPO-20254/12-0074`'s target year is NOT the `2025`
  the malformed string itself carries - measured on the one real instance, its rows' own
  `issue_date` is 2024-12-18, so the true document is `SPO-2024/12-0074`, and `SPO-2025/12-0074`
  is a different, unrelated document that happens to share the same `/12-0074` tail. So a typo
  doc's target year is read off the AGREEING `issue_date` of its own rows (a disagreement, or no
  date evidence at all, is reported and left untouched - guessing would be unsafe). Renamed only
  if that corrected target is absent; if it already exists, reported as
  `typo target exists, manual decision` and left alone - a typo is evidence THIS document's own
  number was mistyped, never evidence it is the same document as whatever already holds the
  corrected number.

  Step B - merge a plain spelling that DOES have an existing target (a genuine twin), one
  document at a time:
    1. Header (`purchase_orders`). The target header survives; `supplier_id`, `issue_date`,
       `expected_date`, `currency`, `source_ref` are filled from the twin where the survivor is
       NULL, and every one of those columns where BOTH sides hold a value and disagree is
       logged as a conflict (the survivor's value is always kept). Every FK column anywhere in
       the database that references `purchase_orders.id` is repointed from the twin's id to the
       survivor's, except `purchase_order_lines.purchase_order_id` (handled by step 2). A twin
       header with no survivor header at all (an allocation-level twin whose header side never
       existed under the target) is renamed in place instead, under the same collision guard as
       Step A.
    2. PO lines (`purchase_order_lines`), matched to an unclaimed survivor line by
       `(product_id, qty_ordered)` then by `product_id` alone (oldest line first). A match logs
       a conflict for every other column that disagrees, repoints every FK referencing the twin
       line's id onto the survivor line's id, then deletes the twin line. No match: the line is
       MOVED onto the survivor header, kept exactly as it is (full row logged first - see
       Backup). Because this step runs BEFORE step 3, an allocation's `po_line_id` already reads
       the repointed value by the time step 3 looks at it - no separate remap table is needed.
    3. Allocations (`spo_allocations`), matched to an unclaimed survivor allocation by
       `(product_id, warehouse_id, allocated_quantity)`, then `(product_id, warehouse_id)`, then
       `product_id` alone (lowest `spo_line_number` first). A match repoints every FK
       referencing the twin allocation's id (discovered at runtime - `picking_lines`,
       `projects.order_inquiry_links`, `scm.order_link_claim` and anything added later) onto the
       survivor's id, copies `inbound_shipment_id` / `created_by` / `allocation_notes` /
       `po_line_id` onto the survivor where it is NULL, and deletes the twin. The survivor's own
       `allocated_quantity` / `quantity_received` / `receipt_status` are never overwritten (the
       book is truth) - a difference is only logged. No match: the allocation is MOVED onto the
       survivor's number with a fresh `next_spo_line_number()` (full row logged first).
    4. `PickingHeaderService.sync_received_for_spo_number` is NEVER called, by any run of this
       script. It has no `source_system` / already-computed guard - it recomputes
       `quantity_received` from approved GRN picking lines and overwrites whatever the survivor
       held, which zeroes the book's own imported receipt figures (measured on the one real
       twin: 15 survivor rows went from 114 received / mixed status to 0 received / `pending`).
       Nothing this script does adds or removes a receipt - it repoints existing FKs and fills
       NULL columns - so there is nothing for a resync to correct, and running one would destroy
       real data instead.
    5. Verify before commit (after the backup JSON is written - see Backup): for every FK this
       run repointed, the count of rows pointing at the survivor id now equals what pointed at
       it before the repoint plus what was moved off the twin id, and zero rows point at the
       twin id afterwards. A plain "does anything still reference the deleted id" check would
       miss a `SET NULL` / `CASCADE` FK entirely - the referencing row would have gone NULL, or
       vanished, rather than still naming the old id, and read as success. Also: zero rows left
       matching the plain/typo regex among what this run touched, and no duplicate
       (company, spo_number, spo_line_number).

Every FK repoint is discovered at runtime from `pg_constraint`, never a hardcoded table list -
`purchase_orders.id` / `purchase_order_lines.id` / `spo_allocations.id` are each referenced by
more tables than the three the plan names by hand (`scm.plan_exception`,
`scm.shipment_line_spo_link`, `projects.order_inquiry_rows`, `scm.loading_plan_line` among
them), and a hardcoded list silently stops covering a table added after this script was
written. The table this runs against is always asked for schema-qualified
(`public.purchase_orders`, not `purchase_orders`) and the resolution is asserted to land on
that exact schema - `projects.purchase_orders` is a DIFFERENT real table, and an unqualified
name is one migration away from becoming ambiguous.

DEVIATION FROM THE PLAN, MEASURED
----------------------------------
The plan describes 230 CRM-created `purchase_orders` headers under the plain SPO spelling.
Measured against the local database (a prod copy, 7 Sep 2026): `purchase_orders.po_number`
carries ZERO rows shaped like `SPO-...` today (one legacy `CRM-SPO-<hex>` row from before doc
numbering existed, which matches neither regex and is untouched by this script). Whatever
cleanup already reached the header side, Step A/B's header handling is still implemented
exactly as specified - a book-only SPO (the overwhelming majority) has no header row on either
spelling and the header step is a no-op for it, which is what actually happens today.
`purchase_order_lines` has no `line_number` column and no line-number unique key at all, so
"renumber if a line-number unique key exists" (step 2's unmatched-line move) has nothing to
renumber; the line is moved with everything else left as it is.

SAFETY / IDEMPOTENCY
---------------------
- `--dry-run` (default) and `--apply` are mutually exclusive - passing both is a CLI error,
  never a silent pick-one.
- Every write in this module is gated behind `apply=True`, so a dry run issues no
  UPDATE/DELETE/INSERT at all - only SELECTs - and still prints the exact per-document plan and
  writes the backup/preview JSON (`"dry_run": true`).
- `--apply` runs the whole thing in ONE transaction; any exception rolls it back completely
  (the caller, `main()`, catches and re-raises after `db.rollback()`). A document whose merge
  raises an `IntegrityError` is reported by number, table and constraint name before the
  original exception re-raises and the whole run unwinds.
- The backup JSON is written BEFORE `_verify_before_commit` runs, so a run the verification
  rejects still leaves the plan file behind for the operator to read.
- `--spo <number>` (repeatable) limits the run to specific documents - either spelling, or the
  exact malformed string for the typo case (which shares no match-key with its target).
  `--out-dir` overrides where the backup JSON lands (default `scripts/out/`; tests point it at
  a throwaway directory). Take a
  `pg_dump -t purchase_orders -t purchase_order_lines -t spo_allocations` first.

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.services.procurement_service import _spo_match_key, next_spo_line_number

#: `(schema-qualified table, column)` - the two columns this script reconciles. Always
#: schema-qualified (S1/S11): `purchase_orders` and `spo_allocations` both exist bare in more
#: than one schema (`projects.purchase_orders`, for one), and an unqualified name is one
#: migration away from silently walking the wrong table.
TABLES: Tuple[Tuple[str, str], ...] = (
    ("public.purchase_orders", "po_number"),
    ("public.spo_allocations", "spo_number"),
)

#: `SPO-202608-0090` -> `SPO-2026/08-0090`.
_PLAIN_RE = re.compile(r"^SPO-(\d{4})(\d{2})-(\d{4})$")
#: `SPO-20254/12-0074` - the stray digit (group 2, unused for the target) is the tell that the
#: whole YEAR was mistyped, not just the separator. The target year comes from the doc's own
#: `issue_date`, never from group 1 - see `_typo_candidates`.
_TYPO_RE = re.compile(r"^SPO-(\d{4})(\d)/(\d{2})-(\d{4})$")


def _target_spelling(raw: Optional[str]) -> Optional[str]:
    """The canonical `SPO-yyyy/mm-xxxx` spelling a PLAIN `raw` should carry, or None if it
    already is one (or matches neither malformed shape this script knows about). Never called
    for the typo shape - its target depends on the row's own data, not the string alone."""
    if not raw:
        return None
    m = _PLAIN_RE.match(raw)
    if m:
        year, month, seq = m.groups()
        return f"SPO-{year}/{month}-{seq}"
    return None


def _resolve_table(db: Session, table: str) -> Tuple[Any, str, str]:
    """The oid, schema and bare name `table` (schema-qualified, e.g. `public.purchase_orders`)
    resolves to - and a hard failure if it resolves to nothing, or to a DIFFERENT schema than
    the caller named (S1): `to_regclass` follows `search_path`, and a same-named table in
    another schema resolving silently would repoint nothing and read as a clean run."""
    if "." not in table:
        raise ValueError(f"_resolve_table requires a schema-qualified name, got {table!r}")
    expected_schema, expected_name = table.split(".", 1)
    row = db.execute(
        text(
            "SELECT c.oid, n.nspname, c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.oid = to_regclass(:t)"
        ),
        {"t": table},
    ).first()
    if row is None:
        raise RuntimeError(f"_resolve_table: {table!r} does not resolve to any table")
    oid, nspname, relname = row
    if nspname != expected_schema or relname != expected_name:
        raise RuntimeError(
            f"_resolve_table: {table!r} resolved to {nspname}.{relname} instead - "
            "refusing an ambiguous schema resolution"
        )
    return oid, nspname, relname


def _referencing_fks(db: Session, table: str, id_column: str = "id") -> List[Tuple[str, str]]:
    """Every `(schema.table, column)` anywhere in the database with a foreign key onto
    `table.id_column`, resolved from `pg_constraint` at RUNTIME rather than a hardcoded list.
    `table` MUST be schema-qualified (see `_resolve_table`). Raises if none are found - every
    real call site (`purchase_orders`, `purchase_order_lines`, `spo_allocations`) has at least
    one, so an empty result means the schema drifted or the caller passed the wrong table, not
    that there is nothing to repoint.
    """
    oid, _nspname, _relname = _resolve_table(db, table)
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
              AND c.confrelid = :oid
              AND ta.attname = :idcol
            ORDER BY 1, 2
            """
        ),
        {"oid": oid, "idcol": id_column},
    ).all()
    fks = [(r[0], r[1]) for r in rows]
    if not fks:
        raise RuntimeError(
            f"_referencing_fks: no foreign keys found referencing {table}.{id_column}"
        )
    return fks


def _candidates(
    db: Session, table: str, column: str, spo_filter: List[str]
) -> List[Tuple[Any, str, str]]:
    """`(company_id, raw, target)` for every distinct PLAIN-shaped value in `table.column`.
    `spo_filter` (either spelling) is pushed into the SQL so a surgical `--spo` run never scans
    rows outside its own scope - load-bearing on the shared dev database, which holds real
    production data."""
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


def _typo_candidates(
    db: Session, table: str, column: str, spo_filter: List[str]
) -> List[Dict[str, Any]]:
    """Every distinct TYPO-shaped value in `table.column`, with its target resolved from the
    doc's own `issue_date` (or a reason it could not be, for the caller to report)."""
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

    out: List[Dict[str, Any]] = []
    for company_id, raw in rows:
        m = _TYPO_RE.match(raw)
        if not m:
            continue
        _year_typed, _stray_digit, month, seq = m.groups()
        years = {
            d.year
            for (d,) in db.execute(
                text(
                    f"SELECT DISTINCT issue_date FROM {table} "
                    f"WHERE company_id = :c AND {column} = :v AND issue_date IS NOT NULL"
                ),
                {"c": company_id, "v": raw},
            ).all()
        }
        if len(years) != 1:
            reason = "issue_date disagreement" if years else "no issue_date evidence"
            out.append(
                {"company_id": company_id, "raw": raw, "target": None, "reason": reason}
            )
            continue
        target = f"SPO-{next(iter(years))}/{month}-{seq}"
        out.append(
            {"company_id": company_id, "raw": raw, "target": target, "reason": None}
        )
    return out


def _exists_value(db: Session, table: str, column: str, company_id: Any, value: str) -> bool:
    row = db.execute(
        text(f"SELECT 1 FROM {table} WHERE company_id = :c AND {column} = :v LIMIT 1"),
        {"c": company_id, "v": value},
    ).first()
    return row is not None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(repr(value))


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {c.name: _jsonable(getattr(row, c.name)) for c in row.__table__.columns}


def _do_rename(
    db: Session,
    apply: bool,
    table: str,
    column: str,
    company_id: Any,
    old: str,
    target: str,
    renames_log: List[Dict[str, Any]],
    skipped_log: List[Dict[str, Any]],
    claimed: set,
    label: str = "rename",
) -> bool:
    """Rename `old` -> `target`, re-checking `target` is still absent right here (S6) - not
    only at classification time. `claimed` is the caller's own in-memory set of
    `(company_id, target)` pairs this run has already taken, seeded fresh per table: two
    malformed spellings racing for the same currently-absent target is real (if rare), and the
    loser is reported rather than crashing on the unique constraint or silently overwriting.
    Returns whether the rename happened."""
    key = (company_id, target)
    if key in claimed or _exists_value(db, table, column, company_id, target):
        print(f"  [{label}] {old} - {target} already claimed this run, manual decision")
        skipped_log.append(
            {"table": table, "column": column, "company_id": str(company_id), "old": old,
             "target": target, "reason": "target claimed by another rename this run"}
        )
        return False

    print(f"[{label}] {table}.{column}: {old} -> {target} (company {company_id})")
    if apply:
        n = db.execute(
            text(
                f"UPDATE {table} SET {column} = :new WHERE company_id = :c AND {column} = :old"
            ),
            {"new": target, "c": company_id, "old": old},
        ).rowcount
        db.flush()
    else:
        n = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE company_id = :c AND {column} = :old"),
            {"c": company_id, "old": old},
        ).scalar()
    renames_log.append(
        {"table": table, "column": column, "company_id": str(company_id),
         "old": old, "new": target, "rows": n}
    )
    claimed.add(key)
    return True


def _repoint(
    db: Session,
    apply: bool,
    ref_table: str,
    ref_col: str,
    old_id: Any,
    new_id: Any,
    log: List[Dict[str, Any]],
) -> int:
    """Repoint one FK column, or (dry run) report how many rows it would touch. `before_new`
    (how many rows already pointed at `new_id` before this repoint) is captured so
    `_verify_before_commit` (S2) can assert the post-merge count is exactly that plus the rows
    just moved - the only way to catch a `SET NULL`/`CASCADE` FK a repoint missed, which a plain
    "does anything still name the deleted id" check cannot (the row went NULL, or vanished,
    instead of still naming it)."""
    before_new = db.execute(
        text(f"SELECT count(*) FROM {ref_table} WHERE {ref_col} = :new"), {"new": new_id}
    ).scalar()
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
                "before_new_count": before_new,
            }
        )
    return n


_HEADER_FILL_COLS = ("supplier_id", "issue_date", "expected_date", "currency", "source_ref")
_PO_LINE_VALUE_COLS = (
    "qty_ordered", "qty_received", "unit_cost", "currency", "expected_date", "discount",
    "line_total", "uom",
)


def _merge_header(
    db: Session,
    apply: bool,
    company_id: Any,
    target: str,
    old_list: List[str],
    doc_backup: Dict[str, Any],
) -> None:
    """Step 1 (+2, nested): merge every `purchase_orders` row under `old_list` into the row
    named `target`, or - when `target` has no header at all - rename the twin in place (the
    same rule Step A applies, for a header-only twin Step A itself never saw)."""
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
        claimed: set = set()
        renames: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for p in p_headers:
            renamed = _do_rename(
                db, apply, "public.purchase_orders", "po_number", company_id, p.po_number,
                target, renames, skipped, claimed, label="header-rename",
            )
            if renamed and apply:
                db.expire(p)
        if renames:
            doc_backup.setdefault("header_renames", []).extend(renames)
        if skipped:
            doc_backup.setdefault("skipped", []).extend(skipped)
        return

    fk_list = [
        fk
        for fk in _referencing_fks(db, "public.purchase_orders")
        if fk != ("public.purchase_order_lines", "purchase_order_id")
    ]

    conflicts = 0
    for p in p_headers:
        print(f"  [header] merging {p.po_number} ({p.id}) into {target} ({s_header.id})")
        doc_backup.setdefault("headers", []).append(_row_to_dict(p))

        for col in _HEADER_FILL_COLS:
            p_val = getattr(p, col)
            s_val = getattr(s_header, col)
            if s_val is None and p_val is not None:
                doc_backup.setdefault("header_fills", []).append(
                    {"column": col, "from_id": str(p.id), "to_id": str(s_header.id),
                     "value": _jsonable(p_val)}
                )
                if apply:
                    setattr(s_header, col, p_val)
            elif s_val is not None and p_val is not None and s_val != p_val:
                doc_backup.setdefault("header_conflicts", []).append(
                    {"column": col, "kept": _jsonable(s_val), "discarded": _jsonable(p_val),
                     "discarded_from_id": str(p.id)}
                )
                conflicts += 1
        if apply:
            db.flush()

        for ref_table, ref_col in fk_list:
            _repoint(db, apply, ref_table, ref_col, p.id, s_header.id,
                     doc_backup.setdefault("fk_repoints", []))

        line_conflicts = _merge_po_lines(db, apply, p.id, s_header.id, doc_backup)
        conflicts += line_conflicts

        doc_backup.setdefault("deleted", []).append({"table": "purchase_orders", "id": str(p.id)})
        if apply:
            db.delete(p)
            db.flush()

    if conflicts:
        print(f"  [conflicts] {conflicts} header/PO-line value conflict(s) logged (survivor kept)")


def _merge_po_lines(
    db: Session, apply: bool, p_header_id: Any, s_header_id: Any, doc_backup: Dict[str, Any]
) -> int:
    """Step 2: match `purchase_order_lines` under the twin header onto unclaimed lines of the
    survivor header, oldest first. A match logs a conflict for every other column that
    disagrees (the survivor's row is what is kept), repoints every FK onto the twin line before
    it is deleted; an unmatched line is MOVED (`purchase_order_lines` has no line-number column
    or unique key to renumber - see the module docstring). Returns the conflict count."""
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
        return 0

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

    conflicts = 0
    fk_list = _referencing_fks(db, "public.purchase_order_lines")
    for p, s in matched:
        doc_backup.setdefault("po_lines", []).append(_row_to_dict(p))
        for col in _PO_LINE_VALUE_COLS:
            p_val, s_val = getattr(p, col), getattr(s, col)
            if p_val != s_val:
                doc_backup.setdefault("po_line_conflicts", []).append(
                    {"column": col, "kept": _jsonable(s_val), "discarded": _jsonable(p_val),
                     "s_id": str(s.id), "p_id": str(p.id)}
                )
                conflicts += 1
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
            {**_row_to_dict(p), "from_header": str(p_header_id), "to_header": str(s_header_id)}
        )
        if apply:
            p.purchase_order_id = s_header_id

    if apply:
        db.flush()
    return conflicts


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
    """Step 3: match `spo_allocations` under the twin number onto unclaimed allocations of the
    survivor number, lowest `spo_line_number` first. A matched twin fills the survivor's NULL
    columns (never overwrites - the book's own figures are truth, a difference is only logged)
    and is deleted; an unmatched twin is MOVED onto the survivor number with a fresh line
    number."""
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

    conflicts = 0
    fk_list = _referencing_fks(db, "public.spo_allocations")
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
                conflicts += 1
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
            {**_row_to_dict(p), "old_spo_number": p.spo_number,
             "old_spo_line_number": p.spo_line_number, "new_spo_number": target,
             "new_spo_line_number": new_line_number}
        )
        if apply:
            p.spo_number = target
            p.spo_line_number = new_line_number

    if apply:
        db.flush()

    if conflicts:
        print(f"  [conflicts] {conflicts} allocation value conflict(s) logged (survivor kept)")


def _merge_document(
    db: Session,
    apply: bool,
    company_id: Any,
    target: str,
    old_list: List[str],
    doc_backup: Dict[str, Any],
    counters: Dict[str, int],
) -> None:
    """Header, then PO lines (nested), then allocations - for ONE document. Wrapped by the
    caller (`run()`) so an `IntegrityError` is reported by document, table and constraint name
    before the original exception re-raises (S7)."""
    _merge_header(db, apply, company_id, target, old_list, doc_backup)
    _merge_allocations(db, apply, company_id, target, old_list, doc_backup, counters)


def _verify_before_commit(db: Session, backup: Dict[str, Any]) -> None:
    """Step 5. Raising here (before `main()` commits) rolls the whole run back. Every check is
    scoped to what THIS RUN actually touched rather than the whole table: a `--spo` surgical
    run - and every test in this suite - leaves the rest of a shared, real database exactly as
    it found it, malformed rows included, and a global scan would both be slow against it and
    fail on pre-existing data this run was never asked to fix. An unfiltered run still gets
    full coverage: `_candidates` already found every malformed row in the table, so "touched"
    already covers all of them.
    """
    touched: set = set()
    for rename in backup.get("renames", []):
        touched.add(rename["old"])
        touched.add(rename["new"])
    for entry in backup.get("merges", []):
        touched.add(entry["target"])
        touched.update(entry.get("old_spellings", []))

        # S2: per repointed FK, the survivor count after must equal what it was before plus
        # what was just moved, and zero rows may still name the deleted id. A plain "still
        # references a deleted id" check cannot see a SET NULL/CASCADE FK a repoint missed -
        # the referencing row went NULL, or vanished, rather than still naming the old id.
        for fk in entry.get("fk_repoints", []):
            after_old = db.execute(
                text(f"SELECT count(*) FROM {fk['table']} WHERE {fk['column']}::text = :old"),
                {"old": fk["old"]},
            ).scalar()
            if after_old:
                raise RuntimeError(
                    f"verification failed: {fk['table']}.{fk['column']} still has {after_old} "
                    f"row(s) naming deleted id {fk['old']}"
                )
            after_new = db.execute(
                text(f"SELECT count(*) FROM {fk['table']} WHERE {fk['column']}::text = :new"),
                {"new": fk["new"]},
            ).scalar()
            expected = fk["before_new_count"] + fk["rows"]
            if after_new != expected:
                raise RuntimeError(
                    f"verification failed: {fk['table']}.{fk['column']} expected {expected} "
                    f"row(s) naming survivor id {fk['new']} (had {fk['before_new_count']} "
                    f"before, moved {fk['rows']}), found {after_new}"
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

        dupes = db.execute(
            text(
                "SELECT company_id, spo_number, spo_line_number, count(*) FROM public.spo_allocations "
                "WHERE spo_number = ANY(:touched) GROUP BY 1, 2, 3 HAVING count(*) > 1"
            ),
            {"touched": list(touched)},
        ).fetchall()
        if dupes:
            raise RuntimeError(
                f"verification failed: duplicate (company, spo_number, spo_line_number): {dupes}"
            )


def _write_backup(backup: Dict[str, Any], out_dir: Optional[str] = None) -> Path:
    directory = Path(out_dir) if out_dir else Path(__file__).parent / "out"
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"dedupe_spo_{ts}_{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(backup, indent=2, default=_jsonable))
    return path


def run(
    db: Session,
    *,
    apply: bool,
    spo_filter: Optional[List[str]] = None,
    out_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Report (and, with `apply=True`, perform) every rename and merge. The caller commits -
    this never calls `db.commit()` or `db.rollback()` itself, so a test can wrap the call in
    its own savepoint and a forced mid-run failure rolls back cleanly."""
    spo_filter = spo_filter or []
    backup: Dict[str, Any] = {
        "dry_run": not apply, "renames": [], "merges": [], "typo_skipped": [],
    }
    counters: Dict[str, int] = {}
    claimed: Dict[str, set] = {t: set() for t, _ in TABLES}

    step_a: List[Tuple[str, str, Any, str, str]] = []
    step_b: Dict[Tuple[Any, str], set] = {}
    for table, column in TABLES:
        for company_id, old, target in _candidates(db, table, column, spo_filter):
            if _exists_value(db, table, column, company_id, target):
                step_b.setdefault((company_id, target), set()).add(old)
            else:
                step_a.append((table, column, company_id, old, target))

    skipped_log = backup.setdefault("skipped", [])
    for table, column, company_id, old, target in step_a:
        renamed = _do_rename(
            db, apply, table, column, company_id, old, target,
            backup["renames"], skipped_log, claimed[table],
        )
        if not renamed:
            # A sibling rename in this same run just took the target - this candidate is a
            # genuine twin of it now, not a lone document (S6).
            step_b.setdefault((company_id, target), set()).add(old)

    # Typo shape: rename-only, its own target (from issue_date), never merged (B3).
    for table, column in TABLES:
        for cand in _typo_candidates(db, table, column, spo_filter):
            company_id, old, target, reason = (
                cand["company_id"], cand["raw"], cand["target"], cand["reason"]
            )
            if reason is None and (
                (company_id, target) in claimed[table]
                or _exists_value(db, table, column, company_id, target)
            ):
                reason = "typo target exists, manual decision"
            if reason:
                print(f"[typo] {table}.{column}: {old} - {reason}")
                backup["typo_skipped"].append(
                    {"table": table, "column": column, "company_id": str(company_id),
                     "raw": old, "target": target, "reason": reason}
                )
                continue
            print(f"[typo-rename] {table}.{column}: {old} -> {target} (company {company_id})")
            if apply:
                n = db.execute(
                    text(
                        f"UPDATE {table} SET {column} = :new "
                        f"WHERE company_id = :c AND {column} = :old"
                    ),
                    {"new": target, "c": company_id, "old": old},
                ).rowcount
                db.flush()
            else:
                n = db.execute(
                    text(
                        f"SELECT count(*) FROM {table} WHERE company_id = :c AND {column} = :old"
                    ),
                    {"c": company_id, "old": old},
                ).scalar()
            backup["renames"].append(
                {"table": table, "column": column, "company_id": str(company_id),
                 "old": old, "new": target, "rows": n}
            )
            claimed[table].add((company_id, target))

    survivor_numbers: set = set()
    for (company_id, target), old_spellings in sorted(
        step_b.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
    ):
        old_list = sorted(old_spellings)
        print(f"[merge] {target} (company {company_id}) <- {old_list}")
        doc_backup: Dict[str, Any] = {
            "company_id": str(company_id), "target": target, "old_spellings": old_list,
        }
        try:
            _merge_document(db, apply, company_id, target, old_list, doc_backup, counters)
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            diag = getattr(orig, "diag", None)
            table_name = getattr(diag, "table_name", None)
            constraint_name = getattr(diag, "constraint_name", None)
            print(
                f"[error] merging {target} (company {company_id}) failed: "
                f"table={table_name or '?'} constraint={constraint_name or '?'}"
            )
            raise
        backup["merges"].append(doc_backup)
        survivor_numbers.add(target)

    # S4: written before verification, so a rejected run still leaves the plan file.
    backup_path = _write_backup(backup, out_dir)

    if apply:
        _verify_before_commit(db, backup)

    return {
        "renamed": len(backup["renames"]),
        "merged_docs": len(step_b),
        "survivor_numbers": sorted(survivor_numbers),
        "backup_path": str(backup_path),
        "backup": backup,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true",
        help="Report only, write nothing (the default; accepted so a run can say so out loud).",
    )
    mode.add_argument("--apply", action="store_true", help="Write the renames and merges.")
    parser.add_argument(
        "--spo", action="append", default=[],
        help="Limit to this SPO number (repeatable). Either spelling; for the rare typo "
             "shape, the exact malformed string.",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="Where the backup/preview JSON is written (default scripts/out/).",
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
        result = run(db, apply=apply, spo_filter=args.spo, out_dir=args.out_dir)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
