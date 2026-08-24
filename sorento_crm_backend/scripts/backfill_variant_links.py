#!/usr/bin/env python3
"""Backfill ``products.variant_of_id`` - the variant graph (suggest-on-miss Wave 1).

Derives every product's parent as the LONGEST EXISTING product whose (dash/ws-
normalized) code is a boundary-prefix of the child's - boundary = the original
next char is a ``-`` or an ASCII letter, never a continued digit. Existence-
anchoring (parent must be a real row) keeps brand/category prefixes like ``ACC``
from forming garbage families. Shares the exact derivation logic with the live
service (``app/services/variant_link_service``: ``normalize_code`` + ``boundary_ok``)
so the one-shot backfill and per-write reconcile can never diverge.

Idempotent "set to correct value" (NOT update-where-null): re-run corrects any
prior wrong value and a clean run reports zero changes (AC-V1).

Run from sorento_crm_backend/:
    python scripts/backfill_variant_links.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict

from sqlalchemy import text

from app.database import SessionLocal
from app.services.variant_link_service import boundary_ok, normalize_code


def derive_parents(rows: list[tuple[str, str]]) -> dict[str, str | None]:
    """rows = [(id, product_code)] -> {id: parent_id or None}, longest boundary
    prefix. In-memory single pass: O(sum(len)) with a norm->id index."""
    # norm -> deterministic representative id (min product_code among collisions).
    norm_to_products: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pid, code in rows:
        norm_to_products[normalize_code(code)].append((code, pid))
    norm_index: dict[str, str] = {}
    for norm, members in norm_to_products.items():
        if not norm:
            continue
        # Tie-break identical to the SQL derive (ORDER BY product_code ASC).
        members.sort(key=lambda m: m[0])
        norm_index[norm] = members[0][1]

    result: dict[str, str | None] = {}
    for pid, code in rows:
        norm_child = normalize_code(code)
        parent: str | None = None
        # Longest prefix first: try len-1 down to 1.
        for plen in range(len(norm_child) - 1, 0, -1):
            prefix = norm_child[:plen]
            cand_id = norm_index.get(prefix)
            if cand_id is None or cand_id == pid:
                continue
            if boundary_ok(code, plen):
                parent = cand_id
                break
        result[pid] = parent
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, product_code, variant_of_id, variant_link_manual FROM products")
        ).fetchall()
        current = {r[0]: r[2] for r in rows}
        code_by_id = {r[0]: r[1] for r in rows}
        # Manually-curated rows are STICKY (D1): never overwrite their variant_of_id.
        # They still act as candidate parents in `derive_parents` (they're in `rows`),
        # only their own value is protected - a re-run reports 0 changes for them.
        manual_ids = {r[0] for r in rows if r[3]}
        derived = derive_parents([(r[0], r[1]) for r in rows])

        changes = {
            pid: parent
            for pid, parent in derived.items()
            if pid not in manual_ids and parent != current.get(pid)
        }

        if not args.dry_run:
            for pid, parent in changes.items():
                db.execute(
                    text("UPDATE products SET variant_of_id = :p WHERE id = :id"),
                    {"p": parent, "id": pid},
                )
            db.commit()

        # Summary.
        n_variants = sum(1 for p in derived.values() if p is not None)
        n_bases = len(derived) - n_variants
        families: dict[str, int] = defaultdict(int)
        for parent in derived.values():
            if parent is not None:
                families[parent] += 1
        top = sorted(families.items(), key=lambda kv: kv[1], reverse=True)[:10]

        mode = "DRY-RUN (no writes)" if args.dry_run else "APPLIED"
        print(f"=== backfill_variant_links [{mode}] ===")
        print(f"products total   : {len(derived)}")
        print(f"variants linked  : {n_variants}")
        print(f"bases            : {n_bases}")
        print(f"rows changed     : {len(changes)}")
        print("top 10 largest families (parent_code -> #direct variants):")
        for parent_id, count in top:
            print(f"  {code_by_id.get(parent_id, parent_id):<28} {count}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
