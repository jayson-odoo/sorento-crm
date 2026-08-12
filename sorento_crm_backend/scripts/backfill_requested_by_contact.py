#!/usr/bin/env python3
"""Backfill purchase_requests.requested_by_contact_id / stock_inquiries.salesperson_contact_id
from the existing free-text `requested_by` / `salesperson` columns.

PLAN-requested-by-contact-routing.md: the requestor FK is the new CS-routing key
(pin lookup keys on the contact the form is FOR, not the submitter). Legacy rows
only ever recorded a free-text name, so this reconciles them the same way any
new portal submission derives the FK: exact contact-name match.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/backfill_requested_by_contact.py [--dry-run] [--batch 500]

Matching rule (case-insensitive EXACT match, never a substring/guess):
- the free text, trimmed and lower-cased, equals a respond_contacts row's
  `name` (trimmed, lower-cased), OR
- it equals `trim(first_name || ' ' || last_name)` (trimmed, lower-cased).
"Eric Ng" -> Eric Ng. "ERIC" -> Eric Ng only if exactly one contact resolves
(e.g. first_name='Eric', no last_name). Two or more contacts resolving to the
same normalized text ("Cindy" matching both Cindy and Cindy Lee) is AMBIGUOUS
and is left untouched -- never guessed.

Idempotent "set where mismatch": a row whose current FK already equals the
resolved contact is left alone (counted separately); a row whose FK is NULL or
points at the WRONG contact is corrected. A second run with unchanged data
reports zero newly-set rows. Ambiguous / unmatched rows are never touched, so a
prior correct value (e.g. set by a portal submission) can never be blanked by
this script.

Covers `purchase_requests` (PR + SF share this table) and `stock_inquiries`.
Does NOT touch `complaints` (out of scope, D11).
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.procurement import PurchaseRequestHeader, StockInquiry


def _build_contact_index(db) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """One pass over respond_contacts -> two lookup dicts keyed by normalized text.

    `by_name`: normalized `name` -> set of contact ids.
    `by_fullname`: normalized `trim(first_name || ' ' || last_name)` -> set of ids.
    A contact can appear under both keys; a text value matches if either yields
    exactly one distinct contact id.
    """
    by_name: dict[str, set[str]] = {}
    by_fullname: dict[str, set[str]] = {}
    for cid, name, first_name, last_name in db.query(
        RespondContact.id, RespondContact.name, RespondContact.first_name, RespondContact.last_name
    ).all():
        if name and name.strip():
            by_name.setdefault(name.strip().lower(), set()).add(cid)
        full = " ".join(p for p in [(first_name or "").strip(), (last_name or "").strip()] if p)
        if full:
            by_fullname.setdefault(full.lower(), set()).add(cid)
    return by_name, by_fullname


def _resolve(
    text_value: Optional[str],
    by_name: dict[str, set[str]],
    by_fullname: dict[str, set[str]],
) -> tuple[Optional[str], str]:
    """Return (contact_id_or_None, status) where status is one of
    'empty' / 'matched' / 'ambiguous' / 'unmatched'."""
    if not text_value or not text_value.strip():
        return None, "empty"
    key = text_value.strip().lower()
    matches = set(by_name.get(key, ())) | set(by_fullname.get(key, ()))
    if len(matches) == 1:
        return next(iter(matches)), "matched"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _backfill_table(
    db,
    *,
    model,
    text_col: str,
    fk_col: str,
    label: str,
    by_name: dict[str, set[str]],
    by_fullname: dict[str, set[str]],
    dry_run: bool,
    batch: int,
    ambiguous_report: list,
    unmatched_report: list,
) -> dict[str, int]:
    stats = {"scanned": 0, "empty": 0, "matched_set": 0, "matched_unchanged": 0, "ambiguous": 0, "unmatched": 0}

    # Keyset batches (id > last_id), NOT `yield_per` + commit -- a mid-loop commit
    # closes the transaction a server-side cursor belongs to. See
    # scripts/backfill_chat_respond_ts.py for the same pattern.
    last_id: Optional[str] = None
    while True:
        q = db.query(model)
        if last_id is not None:
            q = q.filter(model.id > last_id)
        rows = q.order_by(model.id.asc()).limit(batch).all()
        if not rows:
            break
        last_id = rows[-1].id

        for row in rows:
            stats["scanned"] += 1
            text_value = getattr(row, text_col)
            contact_id, status = _resolve(text_value, by_name, by_fullname)

            if status == "empty":
                stats["empty"] += 1
                continue
            if status == "ambiguous":
                stats["ambiguous"] += 1
                ambiguous_report.append((label, row.id, text_value))
                continue
            if status == "unmatched":
                stats["unmatched"] += 1
                unmatched_report.append((label, row.id, text_value))
                continue

            # matched: set-where-mismatch -- corrects a NULL or a prior wrong value,
            # leaves an already-correct FK untouched.
            current = getattr(row, fk_col)
            if str(current or "") == str(contact_id):
                stats["matched_unchanged"] += 1
                continue
            stats["matched_set"] += 1
            if not dry_run:
                # Only assign when actually writing -- a dry-run must not dirty the
                # session (autoflush would otherwise issue the UPDATE anyway).
                setattr(row, fk_col, contact_id)

        if not dry_run:
            db.commit()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True, help="(default) report only, no writes")
    parser.add_argument("--apply", action="store_true", help="perform DB writes (guarded; off by default)")
    parser.add_argument("--batch", type=int, default=500, help="Rows per commit batch (default 500).")
    args = parser.parse_args()
    if args.apply:
        args.dry_run = False

    db = SessionLocal()
    try:
        by_name, by_fullname = _build_contact_index(db)
        all_indexed_ids: set[str] = set()
        for ids in by_name.values():
            all_indexed_ids |= ids
        for ids in by_fullname.values():
            all_indexed_ids |= ids
        print(f"Loaded {len(all_indexed_ids)} distinct contact(s) into the matcher index.")

        ambiguous_report: list = []
        unmatched_report: list = []

        pr_stats = _backfill_table(
            db,
            model=PurchaseRequestHeader,
            text_col="requested_by",
            fk_col="requested_by_contact_id",
            label="purchase_requests",
            by_name=by_name,
            by_fullname=by_fullname,
            dry_run=args.dry_run,
            batch=args.batch,
            ambiguous_report=ambiguous_report,
            unmatched_report=unmatched_report,
        )
        si_stats = _backfill_table(
            db,
            model=StockInquiry,
            text_col="salesperson",
            fk_col="salesperson_contact_id",
            label="stock_inquiries",
            by_name=by_name,
            by_fullname=by_fullname,
            dry_run=args.dry_run,
            batch=args.batch,
            ambiguous_report=ambiguous_report,
            unmatched_report=unmatched_report,
        )

        if args.dry_run:
            db.rollback()

        for label, stats in (("purchase_requests (PR + SF)", pr_stats), ("stock_inquiries", si_stats)):
            print(
                f"\n{label}: scanned={stats['scanned']} empty_text={stats['empty']} "
                f"matched_set={stats['matched_set']} matched_already_correct={stats['matched_unchanged']} "
                f"ambiguous={stats['ambiguous']} unmatched={stats['unmatched']}"
            )

        if ambiguous_report:
            print(f"\nAmbiguous (left NULL, {len(ambiguous_report)} row(s)):")
            for label, row_id, text_value in ambiguous_report:
                print(f"  [{label}] id={row_id} text={text_value!r}")

        if unmatched_report:
            print(f"\nUnmatched (no contact found, {len(unmatched_report)} row(s)):")
            for label, row_id, text_value in unmatched_report:
                print(f"  [{label}] id={row_id} text={text_value!r}")

        print(
            "\n"
            + ("[dry-run] no writes performed." if args.dry_run else "Writes committed.")
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
