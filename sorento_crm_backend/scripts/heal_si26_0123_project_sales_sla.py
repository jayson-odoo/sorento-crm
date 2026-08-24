"""One-off heal: resolve the orphaned project_sales SLA tracker for a stock inquiry.

Root cause: `_active_tracker` previously matched on policy_id (a create-time snapshot).
A stage's policy was edited after the tracker existed, so the resolve event
(pending_project_sales -> pending_purchasing) could not find the live tracker and it
stuck at Escalated. Code is now fixed for future events; this heals the already-stuck row.

Resolved/responded timestamps are taken from the audit log entry that recorded the
status change to pending_purchasing (the moment the resolve event actually fired), NOT
now(). response_time + resolution_duration are auto-computed by update_tracking from
initiated_at.

Run:  DRY (default) ->  venv/bin/python scripts/heal_si26_0123_project_sales_sla.py
      APPLY         ->  venv/bin/python scripts/heal_si26_0123_project_sales_sla.py --apply
Optional: --inquiry SI26-0123  --team-set project_sales
"""
from __future__ import annotations

import argparse
import sys

from app.database import SessionLocal
from app.models.audit import AuditLog
from app.models.sla import ConversationSLATracking
from app.schemas.sla import ConversationSLATrackingUpdate
from app.services.sla_service import ConversationSLATrackingService

SOURCE_ENTITY_TYPE = "stock_inquiry"
TARGET_OLD_STATUS = "pending_project_sales"
TARGET_NEW_STATUS = "pending_purchasing"


def _find_inquiry_id(db, inquiry_number: str) -> str | None:
    """Resolve the stock_inquiry row id from its human number via the audit trail
    (inquiry_number: - -> SI26-0123 insert), avoiding a hard import of the SI model."""
    row = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == SOURCE_ENTITY_TYPE,
            AuditLog.new_values["inquiry_number"].astext == inquiry_number,
        )
        .order_by(AuditLog.changed_at.asc())
        .first()
    )
    return row.entity_id if row else None


def _transition_time(db, inquiry_id: str):
    """changed_at of the audit row recording status -> pending_purchasing."""
    row = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == SOURCE_ENTITY_TYPE,
            AuditLog.entity_id == inquiry_id,
            AuditLog.new_values["status"].astext == TARGET_NEW_STATUS,
            AuditLog.old_values["status"].astext == TARGET_OLD_STATUS,
        )
        .order_by(AuditLog.changed_at.desc())
        .first()
    )
    return row.changed_at if row else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inquiry", default="SI26-0123")
    ap.add_argument("--team-set", default="project_sales")
    ap.add_argument("--apply", action="store_true", help="commit; omit for dry-run")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        inquiry_id = _find_inquiry_id(db, args.inquiry)
        if not inquiry_id:
            print(f"ABORT: no stock_inquiry found for {args.inquiry}")
            return 1
        print(f"inquiry {args.inquiry} -> id {inquiry_id}")

        resolve_at = _transition_time(db, inquiry_id)
        if not resolve_at:
            print(
                f"ABORT: no audit row for status {TARGET_OLD_STATUS} -> {TARGET_NEW_STATUS}"
            )
            return 1
        print(f"transition (resolve/respond) time [UTC-naive]: {resolve_at}")

        tracker = (
            db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == SOURCE_ENTITY_TYPE,
                ConversationSLATracking.source_entity_id == str(inquiry_id),
                ConversationSLATracking.team_set_code == args.team_set,
                ConversationSLATracking.is_resolved.is_(False),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )
        if not tracker:
            print(
                f"ABORT: no unresolved tracker for team_set '{args.team_set}' "
                "(already healed?)"
            )
            return 1

        print(
            f"tracker {tracker.id}: tier={tracker.current_tier} "
            f"initiated_at={tracker.initiated_at} is_responded={tracker.is_responded} "
            f"escalated_at={tracker.escalated_at}"
        )

        if not args.apply:
            print("\nDRY RUN - would set is_resolved=True, is_responded=True,")
            print(f"  resolved_at = responded_at = {resolve_at}")
            print("  (response_time + resolution_duration auto-computed from initiated_at)")
            print("Re-run with --apply to commit.")
            return 0

        svc = ConversationSLATrackingService(db)
        svc.update_tracking(
            str(tracker.id),
            ConversationSLATrackingUpdate(
                is_resolved=True,
                is_responded=True,
                resolved_at=resolve_at,
                responded_at=resolve_at,
            ),
        )
        db.commit()
        db.refresh(tracker)
        print(
            f"\nHEALED. is_resolved={tracker.is_resolved} resolved_at={tracker.resolved_at} "
            f"responded_at={tracker.responded_at} response_time={tracker.response_time} "
            f"resolution_duration={tracker.resolution_duration}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
