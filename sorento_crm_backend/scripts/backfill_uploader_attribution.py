#!/usr/bin/env python3
"""Backfill attachments.uploader_kind / attachments.uploaded_by_contact_id.

PLAN-response-attachments-and-portal-nav.md S1: `attachments.uploaded_by` only
ever held a `users.id`, and the portal upload path called
`create_attachment_and_link(..., created_by=None)` -- so a contact upload and
"we don't know" were indistinguishable (both NULL). These two new columns make
"by contact" vs "by user" derivable; this script reconciles existing rows the
same way the live upload paths now stamp new ones.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/backfill_uploader_attribution.py [--dry-run] [--batch 500]

Rule, scoped to attachments whose `entity_type` is a FORM type (complaint /
purchase_request [PR + SF share this entity_type] / stock_inquiry -- each of
which carries its own `contact_id`):

- `uploaded_by IS NULL`  -> `uploader_kind='contact'`; `uploaded_by_contact_id`
  is set from the parent form row's `contact_id`, but ONLY when that parent
  row exists and actually has one (never guessed; a missing contact_id is
  left NULL and counted separately).
- `uploaded_by IS NOT NULL` -> `uploader_kind='user'`.
- Any other `entity_type` (product photos, resource files, worker-created
  rows, etc.) is left completely untouched -- only counted.

Idempotent "set where mismatch": a row already carrying the correct
`uploader_kind` / `uploaded_by_contact_id` is left alone (counted separately);
a NULL or a prior wrong value is corrected. A second run with unchanged data
reports zero newly-set rows.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.complaints import Complaint
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.models.resources import Attachment

# entity_type -> parent model. Every one of these tables carries its own
# `contact_id` TEXT column (the submitting respond contact). `purchase_request`
# covers BOTH purchase_request and sponsorship_form rows -- they share the
# `purchase_requests` table and this entity_type on attachments.
FORM_ENTITY_PARENTS: dict[str, type] = {
    "complaint": Complaint,
    "purchase_request": PurchaseRequestHeader,
    "stock_inquiry": StockInquiry,
}


def _parent_contact_id(db, entity_type: str, entity_id: Optional[str], cache: dict) -> Optional[str]:
    """The parent form row's contact_id, or None if the row/column is missing.

    Cached per (entity_type, entity_id) so re-scanning many attachments on the
    same form (a common case) doesn't re-query per row.
    """
    if not entity_id:
        return None
    key = (entity_type, entity_id)
    if key in cache:
        return cache[key]
    model = FORM_ENTITY_PARENTS.get(entity_type)
    value: Optional[str] = None
    if model is not None:
        parent = db.query(model).filter(model.id == entity_id).first()
        if parent is not None:
            cid = getattr(parent, "contact_id", None)
            value = str(cid) if cid else None
    cache[key] = value
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True, help="(default) report only, no writes")
    parser.add_argument("--apply", action="store_true", help="perform DB writes (guarded; off by default)")
    parser.add_argument("--batch", type=int, default=500, help="Rows per commit batch (default 500).")
    args = parser.parse_args()
    if args.apply:
        args.dry_run = False

    db = SessionLocal()
    stats = {
        "scanned": 0,
        "other_entity_type_skipped": 0,
        "contact_kind_set": 0,
        "contact_id_set": 0,
        "contact_no_parent_contact": 0,
        "contact_already_correct": 0,
        "user_kind_set": 0,
        "user_already_correct": 0,
    }
    parent_contact_cache: dict = {}
    try:
        q = db.query(Attachment)
        # Keyset batches (id > last_id), NOT `yield_per` + commit -- see
        # scripts/backfill_chat_respond_ts.py for why the two are incompatible.
        last_id: Optional[str] = None
        while True:
            rows_q = q
            if last_id is not None:
                rows_q = rows_q.filter(Attachment.id > last_id)
            rows = rows_q.order_by(Attachment.id.asc()).limit(args.batch).all()
            if not rows:
                break
            last_id = rows[-1].id

            for row in rows:
                stats["scanned"] += 1
                entity_type = (row.entity_type or "").strip()
                if entity_type not in FORM_ENTITY_PARENTS:
                    stats["other_entity_type_skipped"] += 1
                    continue

                if row.uploaded_by is not None:
                    if row.uploader_kind != "user":
                        stats["user_kind_set"] += 1
                        if not args.dry_run:
                            row.uploader_kind = "user"
                    else:
                        stats["user_already_correct"] += 1
                    continue

                # uploaded_by IS NULL -> contact upload.
                contact_id = _parent_contact_id(
                    db, entity_type, row.entity_id, parent_contact_cache
                )
                kind_changes = row.uploader_kind != "contact"
                id_changes = bool(contact_id) and str(row.uploaded_by_contact_id or "") != str(contact_id)
                if not contact_id:
                    stats["contact_no_parent_contact"] += 1
                if kind_changes:
                    stats["contact_kind_set"] += 1
                if id_changes:
                    stats["contact_id_set"] += 1
                if not (kind_changes or id_changes):
                    stats["contact_already_correct"] += 1
                if not args.dry_run:
                    if kind_changes:
                        row.uploader_kind = "contact"
                    if id_changes:
                        row.uploaded_by_contact_id = contact_id

            if not args.dry_run:
                db.commit()

        if args.dry_run:
            db.rollback()

        print(
            "scanned={scanned} other_entity_type_skipped={other_entity_type_skipped}\n"
            "user-uploaded: kind_set={user_kind_set} already_correct={user_already_correct}\n"
            "contact-uploaded: kind_set={contact_kind_set} contact_id_set={contact_id_set} "
            "already_correct={contact_already_correct} no_parent_contact_found={contact_no_parent_contact}".format(
                **stats
            )
        )
        print("[dry-run] no writes performed." if args.dry_run else "Writes committed.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
