#!/usr/bin/env python3
"""Snapshot / inspect / undo a Container Status import trial in production.

For trying the feature on live data and putting everything back afterwards.

**Snapshot BEFORE the trial import, or there is nothing to restore to.** "Unset
the dates I changed" cannot be done from the after-state alone: the import
writes the same 20 columns whether they were empty or already held a value an
office user typed by hand months ago, and blanking all of them would destroy
real data alongside the trial's. So the undo is a restore to a recorded state,
never a blanket clear.

    # 1. before uploading anything
    python scripts/container_status_trial.py snapshot

    # 2. upload the workbook in the UI, test the feature, then look at the damage
    python scripts/container_status_trial.py status

    # 3. put it back
    python scripts/container_status_trial.py restore --dry-run
    python scripts/container_status_trial.py restore

What `restore` undoes:

* every clearance column the import can write, back to its snapshot value
  (including back to NULL, which is the whole point)
* `source_sheet`, which the import stamps per row
* Container Status attachments created after the snapshot: hard-deleted, and
  their storage object left alone (the import job still references it)
* Container Status attachments the trial TRASHED (the one-live-workbook rule):
  un-trashed, because they were live when the snapshot was taken
* optionally the `import_jobs` rows for the trial, with `--purge-jobs`

What it deliberately does NOT undo:

* the migrations (columns, checkpoint rows, access-agent field rows). Those are
  the deploy, not the trial, and dropping them is a `alembic downgrade`.
* per-contact attachment-type grants. If you grant one to test the MCP path,
  revoke it in the UI - it is one tick, and guessing which grants predate the
  trial is exactly the kind of assumption that deletes a real one.

The snapshot file is JSON, written next to the script by default. Keep it until
the trial is over; without it `restore` refuses to run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid as _uuid
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import SessionLocal
from app.services.container_status_import import FIELD_MAP

#: Every column the import can write. Derived from the importer's own map, so a
#: new imported column is covered here the day it is added rather than silently
#: surviving a "restore".
CLEARANCE_COLUMNS: tuple[str, ...] = tuple(sorted(set(FIELD_MAP.values()) | {"source_sheet"}))

DEFAULT_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "container_status_trial_snapshot.json"
)

TYPE_NAME = "Container Status"


def _json_safe(value):
    """Make a DB value round-trip through JSON.

    UUID and date columns come back as objects; the snapshot has to survive a
    write and a read and still compare equal to a freshly-read row, so both
    sides are normalized to strings.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, _uuid.UUID):
        return str(value)
    return value


def _shipment_rows(db) -> list[dict]:
    cols = ", ".join(CLEARANCE_COLUMNS)
    rows = db.execute(
        text(f"SELECT id, {cols} FROM inbound_shipments ORDER BY id")
    ).mappings().all()
    return [{k: _json_safe(v) for k, v in row.items()} for row in rows]


def _workbook_rows(db) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT a.id, a.file_path, a.is_deleted, a.uploaded_at
            FROM attachments a
            JOIN attachment_types t ON t.id = a.attachment_type_id
            WHERE t.type_name = :name
            ORDER BY a.uploaded_at
            """
        ),
        {"name": TYPE_NAME},
    ).mappings().all()
    return [{k: _json_safe(v) for k, v in row.items()} for row in rows]


def _load(path: str) -> dict:
    if not os.path.exists(path):
        raise SystemExit(
            f"No snapshot at {path}. Run `snapshot` BEFORE the trial import - "
            "the pre-trial values cannot be reconstructed afterwards."
        )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_snapshot(args) -> int:
    db = SessionLocal()
    try:
        payload = {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "columns": list(CLEARANCE_COLUMNS),
            "shipments": _shipment_rows(db),
            "workbooks": _workbook_rows(db),
        }
    finally:
        db.close()

    if os.path.exists(args.file) and not args.force:
        raise SystemExit(
            f"{args.file} already exists. Restore from it first, or pass --force "
            "to overwrite (which discards the earlier pre-trial state)."
        )
    with open(args.file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)

    filled = sum(
        1
        for row in payload["shipments"]
        if any(row[c] is not None for c in CLEARANCE_COLUMNS)
    )
    print(f"Snapshot written to {args.file}")
    print(f"  {len(payload['shipments'])} shipments ({filled} already carry clearance data)")
    print(f"  {len(payload['workbooks'])} existing {TYPE_NAME} attachment(s)")
    return 0


def _diff(db, snapshot: dict) -> tuple[list[tuple[str, dict]], list[dict], list[dict]]:
    """Return (changed_shipments, new_workbooks, trashed_workbooks)."""
    before = {row["id"]: row for row in snapshot["shipments"]}
    changed: list[tuple[str, dict]] = []
    for row in _shipment_rows(db):
        prior = before.get(row["id"])
        if prior is None:
            continue  # a shipment created after the snapshot: not ours to touch
        deltas = {c: (prior[c], row[c]) for c in CLEARANCE_COLUMNS if prior[c] != row[c]}
        if deltas:
            changed.append((row["id"], deltas))

    known = {w["id"]: w for w in snapshot["workbooks"]}
    now = _workbook_rows(db)
    new = [w for w in now if w["id"] not in known]
    trashed = [
        w
        for w in now
        if w["id"] in known and w["is_deleted"] and not known[w["id"]]["is_deleted"]
    ]
    return changed, new, trashed


def cmd_status(args) -> int:
    snapshot = _load(args.file)
    db = SessionLocal()
    try:
        changed, new, trashed = _diff(db, snapshot)
    finally:
        db.close()

    print(f"Snapshot taken {snapshot['taken_at']}")
    print(f"  shipments changed since:      {len(changed)}")
    print(f"  new {TYPE_NAME} attachments:  {len(new)}")
    print(f"  pre-existing ones trashed:    {len(trashed)}")
    for shipment_id, deltas in changed[: args.show]:
        print(f"\n  {shipment_id}")
        for col, (was, now) in deltas.items():
            print(f"    {col}: {was!r} -> {now!r}")
    if len(changed) > args.show:
        print(f"\n  ... and {len(changed) - args.show} more (raise --show to see them)")
    return 0


def cmd_restore(args) -> int:
    snapshot = _load(args.file)
    before = {row["id"]: row for row in snapshot["shipments"]}
    db = SessionLocal()
    try:
        changed, new, trashed = _diff(db, snapshot)

        print(f"Restoring to the snapshot taken {snapshot['taken_at']}")
        print(f"  {len(changed)} shipment(s) to revert")
        print(f"  {len(new)} attachment(s) to delete")
        print(f"  {len(trashed)} attachment(s) to un-trash")
        if args.purge_jobs:
            print("  and the trial's import_jobs rows")

        if args.dry_run:
            print("\nDry run - nothing written.")
            return 0

        assignments = ", ".join(f"{c} = :{c}" for c in CLEARANCE_COLUMNS)
        for shipment_id, _deltas in changed:
            params = {c: before[shipment_id][c] for c in CLEARANCE_COLUMNS}
            params["id"] = shipment_id
            db.execute(
                text(f"UPDATE inbound_shipments SET {assignments} WHERE id = :id"), params
            )

        job_keys: list[str] = []
        for workbook in new:
            # Hard delete: this row did not exist before the trial, so trashing it
            # would leave the library holding a file nobody asked for.
            job_keys.append(workbook["file_path"])
            db.execute(text("DELETE FROM attachments WHERE id = :id"), {"id": workbook["id"]})

        for workbook in trashed:
            # Trashed by the one-live-workbook rule during the trial. It was live
            # when the snapshot was taken, so it goes back.
            db.execute(
                text(
                    "UPDATE attachments SET is_deleted = false, deleted_at = NULL "
                    "WHERE id = :id"
                ),
                {"id": workbook["id"]},
            )

        if args.purge_jobs and job_keys:
            # Suffix match: file_path holds the CDN URL, import_jobs holds the key.
            for file_path in job_keys:
                db.execute(
                    text(
                        "DELETE FROM import_jobs WHERE source_file_key IS NOT NULL "
                        "AND :path LIKE '%' || source_file_key"
                    ),
                    {"path": file_path},
                )

        db.commit()
        print("\nDone.")

        leftover, still_new, still_trashed = _diff(db, snapshot)
        if leftover or still_new or still_trashed:
            print(
                f"WARNING: {len(leftover)} shipment(s), {len(still_new)} new and "
                f"{len(still_trashed)} trashed attachment(s) still differ."
            )
        else:
            print("Verified: the database matches the snapshot.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--file", default=DEFAULT_SNAPSHOT, help="snapshot path (default: beside this script)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="record the pre-trial state")
    snap.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    snap.set_defaults(func=cmd_snapshot)

    stat = sub.add_parser("status", help="show what the trial changed")
    stat.add_argument("--show", type=int, default=10, help="how many shipments to print")
    stat.set_defaults(func=cmd_status)

    undo = sub.add_parser("restore", help="put everything back")
    undo.add_argument("--dry-run", action="store_true")
    undo.add_argument(
        "--purge-jobs",
        action="store_true",
        help="also delete the trial's import_jobs rows (the retained upload goes with them)",
    )
    undo.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
