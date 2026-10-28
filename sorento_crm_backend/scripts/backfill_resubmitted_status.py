#!/usr/bin/env python3
"""Relabel existing resubmissions as `resubmitted` (RESUBMITTED-STATUS, owner ruling Q5).

Before this lane a submit that answered a rejection landed back on the review stage. Only the
rows where the data PROVES that their current submission answered a rejection are relabelled:

* complaint            status 'submitted' and `rejected_at` still set (a portal resubmit keeps
                       it; approving clears it).
* new product app      status 'submitted' and `reject_reason` still set (submit keeps it;
                       approve and revise clear it).
* purchase request /   status 'submitted', no approval decision since, and the newest audited
  sponsorship form     status change on the row was rejected -> submitted.
* stock inquiry        status 'pending_project_sales' and the newest audited status change on
                       the row was rejected -> pending_project_sales.
* quotation            on the `pending_approval` rung, and the approval event before its newest
                       "requested" one is a "rejected" one (the project activity feed).

Project registrations and dealer-kit Editions are NOT relabelled: neither keeps an audit trail
nor a field that survives the resubmit, so nothing proves which pending ones were resubmits.

Run from sorento_crm_backend/:
    python scripts/backfill_resubmitted_status.py                 # dry run: counts + samples
    python scripts/backfill_resubmitted_status.py --apply --out relabelled.json
    python scripts/backfill_resubmitted_status.py --revert relabelled.json

SAFETY: dry run is the default and makes zero writes. --apply writes, in one transaction, and
records exactly which rows it changed (and from what) so --revert puts them back.
Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

# form -> (candidate query returning id, reference, table, status column, from value)
_QUOTATION_RUNG = (
    "(SELECT id FROM statuses WHERE entity_type = 'quotation' AND key = '{key}' "
    "AND scope_id IS NULL)"
)

_LATEST_STATUS_CHANGE = """(
    SELECT a.old_values ->> 'status' FROM audit_logs a
    WHERE a.entity_type = '{entity}' AND a.entity_id = t.id::text AND a.action = 'UPDATE'
      AND a.new_values ? 'status'
    ORDER BY a.changed_at DESC LIMIT 1
)"""

FORMS = {
    "complaint": (
        "SELECT t.id::text, t.complaint_number FROM complaints t "
        "WHERE t.status = 'submitted' AND t.rejected_at IS NOT NULL",
        "complaints",
        "status",
        "submitted",
    ),
    "new_product_application": (
        "SELECT t.id::text, t.application_no FROM new_product_applications t "
        "WHERE t.status = 'submitted' AND NULLIF(btrim(t.reject_reason), '') IS NOT NULL",
        "new_product_applications",
        "status",
        "submitted",
    ),
    "purchase_request": (
        "SELECT t.id::text, t.request_number FROM purchase_requests t "
        "WHERE t.status = 'submitted' AND COALESCE(t.approval_status, '') = '' "
        f"AND {_LATEST_STATUS_CHANGE.format(entity='purchase_request')} = 'rejected'",
        "purchase_requests",
        "status",
        "submitted",
    ),
    "stock_inquiry": (
        "SELECT t.id::text, t.inquiry_number FROM stock_inquiries t "
        "WHERE t.status = 'pending_project_sales' "
        f"AND {_LATEST_STATUS_CHANGE.format(entity='stock_inquiry')} = 'rejected'",
        "stock_inquiries",
        "status",
        "pending_project_sales",
    ),
    "quotation": (
        "SELECT t.id::text, t.document_no FROM projects.quotation_documents t "
        f"WHERE t.approval_status_id = {_QUOTATION_RUNG.format(key='pending_approval')} "
        "AND (SELECT e.system_template FROM activity_events e "
        "     WHERE e.entity_type = 'project' AND e.entity_id = t.project_id::text "
        "       AND e.system_payload ->> 'document_id' = t.id::text "
        "       AND e.system_template IN ('quotation_approval_requested', "
        "           'quotation_approval_rejected', 'quotation_approval_granted', "
        "           'quotation_approval_revised') "
        "     ORDER BY e.created_at DESC, e.id DESC OFFSET 1 LIMIT 1"
        ") = 'quotation_approval_rejected'",
        "projects.quotation_documents",
        "approval_status_id",
        None,  # a status id, resolved per database
    ),
}


def candidates(conn) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for form, (query, *_rest) in FORMS.items():
        out[form] = [(row[0], row[1] or row[0]) for row in conn.execute(text(query)).all()]
    return out


def _quotation_rung(conn, key: str):
    return conn.execute(text(_QUOTATION_RUNG.format(key=key))).scalar()


def apply(conn, found: dict[str, list[tuple[str, str]]]) -> dict:
    """Relabel every candidate. Returns the record --revert needs."""
    record: dict = {}
    for form, rows in found.items():
        if not rows:
            continue
        _query, table, column, from_value = FORMS[form]
        if form == "quotation":
            from_value = _quotation_rung(conn, "pending_approval")
            to_value = _quotation_rung(conn, "resubmitted")
            if to_value is None:
                print("quotation: the graph has no resubmitted rung; run the migration first")
                continue
        else:
            to_value = "resubmitted"
        ids = [row[0] for row in rows]
        conn.execute(
            text(f"UPDATE {table} SET {column} = :to WHERE id::text = ANY(:ids) AND {column} = :frm"),
            {"to": to_value, "ids": ids, "frm": from_value},
        )
        record[form] = {"table": table, "column": column, "from": from_value, "to": to_value, "ids": ids}
    return record


def revert(conn, record: dict) -> None:
    allowed = {(table, column) for _query, table, column, _from in FORMS.values()}
    for form, entry in record.items():
        if (entry["table"], entry["column"]) not in allowed:
            raise SystemExit(f"{form}: {entry['table']}.{entry['column']} is not a column this script writes")
        conn.execute(
            text(
                f"UPDATE {entry['table']} SET {entry['column']} = :frm "
                f"WHERE id::text = ANY(:ids) AND {entry['column']} = :to"
            ),
            {"frm": entry["from"], "to": entry["to"], "ids": entry["ids"]},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the relabel (default: dry run)")
    parser.add_argument("--out", default="resubmitted_backfill.json", help="where --apply records what it changed")
    parser.add_argument("--revert", metavar="FILE", help="undo a previous --apply from its record")
    args = parser.parse_args()

    from app.database import engine

    with engine.begin() as conn:
        if args.revert:
            with open(args.revert) as handle:
                revert(conn, json.load(handle))
            print(f"reverted from {args.revert}")
            return 0
        found = candidates(conn)
        for form, rows in found.items():
            sample = ", ".join(ref for _id, ref in rows[:5])
            print(f"{form}: {len(rows)}" + (f"  e.g. {sample}" if sample else ""))
        if not args.apply:
            print("dry run: nothing written (pass --apply to relabel)")
            return 0
        record = apply(conn, found)
        with open(args.out, "w") as handle:
            json.dump(record, handle, indent=2)
        print(f"relabelled; record written to {args.out} (undo with --revert {args.out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
