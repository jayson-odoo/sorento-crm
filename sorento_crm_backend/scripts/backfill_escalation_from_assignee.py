"""Backfill conversation_sla_event_log.from_assigned_to_id for historical escalations.

Best-effort, RECONSTRUCTIVE heuristic (PLAN-form-banner-person-links §4, Risk R2):
for each escalation event that predates the column (from_assigned_to_id IS NULL),
set it to the ``assigned_to_id`` of the immediately-prior event-log row for the same
``sla_tracking_id`` ordered by ``event_at`` ASC (SQL window ``LAG``). Escalation rows
with no prior event stay NULL.

This is NOT authoritative: it breaks when a mid-tier reassignment wrote an intervening
non-escalation event that changed the assignee between escalations. Every row set and
every row left NULL is counted in the summary. Go-forward escalations are snapshotted
structurally at write time and never need this.

Idempotent: only touches rows still NULL; a second run reports 0 set.

Usage:
    python scripts/backfill_escalation_from_assignee.py [--dry-run]
"""
import sys

from sqlalchemy import text

from app.database import SessionLocal


# For every escalation row still NULL, compute the prior event's assigned_to_id via LAG.
_SELECT_CANDIDATES = text(
    """
    WITH ordered AS (
        SELECT
            id,
            event_type,
            from_assigned_to_id,
            LAG(assigned_to_id) OVER (
                PARTITION BY sla_tracking_id ORDER BY event_at ASC, created_at ASC
            ) AS prev_assigned_to_id
        FROM conversation_sla_event_log
    )
    SELECT id, prev_assigned_to_id
    FROM ordered
    WHERE event_type = 'escalation'
      AND from_assigned_to_id IS NULL
    """
)

_UPDATE_ONE = text(
    "UPDATE conversation_sla_event_log "
    "SET from_assigned_to_id = :prev WHERE id = :id"
)


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    set_count = 0
    left_null = 0
    try:
        rows = db.execute(_SELECT_CANDIDATES).fetchall()
        for row in rows:
            event_id = row[0]
            prev = row[1]
            if prev is None or not str(prev).strip():
                left_null += 1
                continue
            if not dry_run:
                db.execute(_UPDATE_ONE, {"prev": str(prev), "id": event_id})
            set_count += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    summary = {
        "escalations_scanned": set_count + left_null,
        "from_assigned_to_id_set": set_count,
        "left_null_no_prior_assignee": left_null,
        "dry_run": dry_run,
    }
    print(summary)
    return summary


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
