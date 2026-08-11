"""Post-grace undo: eligibility guardrail, tracker void + reopen (AC-PG*, AC-PGE*).

The guardrail lives here, in one place, and is used by BOTH the eligibility read and the
execute path. If the read and the write computed it separately they would eventually
disagree, and the FE would render a button the server refuses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sla import SlaFormAction

logger = logging.getLogger(__name__)


# Machine-readable refusal reasons. The FE maps them to copy; the server owns the truth.
BLOCK_NO_ACTION = "no_action"
BLOCK_NEXT_STAGE_ACTED = "next_stage_acted"
BLOCK_STATUS_MOVED = "status_moved"
BLOCK_NOT_INVERTIBLE = "not_invertible"
BLOCK_NO_PERMISSION = "no_permission"
BLOCK_ACTION_PENDING = "action_pending"


@dataclass
class UndoEligibility:
    can_undo: bool
    action: Optional[SlaFormAction] = None
    blocked_reason: Optional[str] = None
    blocked_by_name: Optional[str] = None
    blocked_at: Optional[datetime] = None

    def to_payload(self) -> dict:
        from app.services.form_action_registry import get_action

        registered = get_action(self.action.action_key) if self.action else None
        return {
            "can_undo": self.can_undo,
            "action_key": self.action.action_key if self.action else None,
            "action_label": registered.label if registered else None,
            "committed_at": (
                self.action.committed_at.isoformat()
                if self.action and self.action.committed_at
                else None
            ),
            "blocked_reason": self.blocked_reason,
            "blocked_by_name": self.blocked_by_name,
            "blocked_at": self.blocked_at.isoformat() if self.blocked_at else None,
            "tells_contact": bool(registered.tells_contact) if registered else False,
        }


def _user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == str(user_id)).first()
    return ((user.name or user.email) if user else None) or None


def _entity_status(db: Session, source_entity_type: str, source_entity_id: str):
    """The form's CURRENT lifecycle status, or None when the row is gone.

    The guardrail cannot rely on sibling `sla_form_actions` rows alone: the void
    routes (and any future endpoint that skips the dispatcher) change the entity
    without writing an action row, so "the last committed action" can predate a
    transition the history never saw. Undoing on top of that would, e.g., silently
    un-void a voided form while `voided_by`/`void_reason` stay populated.
    """
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry
    from app.models.tickets import Ticket

    model = {
        "purchase_request": PurchaseRequestHeader,
        "sponsorship_form": PurchaseRequestHeader,
        "stock_inquiry": StockInquiry,
        "complaint": Complaint,
        "ticket": Ticket,
    }.get(source_entity_type)
    if model is None:
        return None
    row = db.query(model.status).filter(model.id == str(source_entity_id)).first()
    return (str(row[0]).strip().lower() or None) if row and row[0] else None


def evaluate(
    db: Session,
    *,
    source_entity_type: str,
    source_entity_id: str,
    has_permission: bool,
) -> UndoEligibility:
    """Can the last committed action on this form be reversed right now?

    Only the LAST committed action is ever a candidate (AC-PG-1) and there is no time
    limit - the guardrail, not a clock, is what stands between a stale form and a
    rewind, which is why it is the most heavily tested thing in this feature.
    """
    from app.models.sla import ConversationSLATracking
    from app.services.form_action_registry import get_action
    from app.services.form_action_service import FormActionService

    service = FormActionService(db)

    # A NEW action parked on this form makes the last committed one off-limits: undoing
    # underneath it changes the premise the pending action was requested on. The FE
    # never offers Undo while something is pending, but the API must refuse too - the
    # two writers would otherwise race on one form (AC-PGE-6's sibling).
    if service.pending_for(source_entity_type, source_entity_id) is not None:
        return UndoEligibility(can_undo=False, blocked_reason=BLOCK_ACTION_PENDING)

    action_row = service.last_committed(source_entity_type, source_entity_id)
    if action_row is None:
        return UndoEligibility(can_undo=False, blocked_reason=BLOCK_NO_ACTION)

    # A voided (or deleted) form is terminal through a route that never writes an
    # action row, so the sibling-row checks below cannot see the transition. Undo
    # would restore pre-action state OVER the void, silently un-voiding the form.
    current_status = _entity_status(db, source_entity_type, source_entity_id)
    if current_status is None or current_status == "voided":
        return UndoEligibility(
            can_undo=False, action=action_row, blocked_reason=BLOCK_STATUS_MOVED
        )

    registered = get_action(action_row.action_key)
    if registered is None or registered.invert is None:
        return UndoEligibility(
            can_undo=False, action=action_row, blocked_reason=BLOCK_NOT_INVERTIBLE
        )

    if not has_permission:
        return UndoEligibility(
            can_undo=False, action=action_row, blocked_reason=BLOCK_NO_PERMISSION
        )

    # The stage this action opened. If anyone has touched it, undoing would throw away
    # real work, so it is refused and the refusal names who and when (AC-PG-2).
    if action_row.spawned_tracking_id:
        spawned = (
            db.query(ConversationSLATracking)
            .filter(ConversationSLATracking.id == str(action_row.spawned_tracking_id))
            .first()
        )
        if spawned is not None:
            if bool(getattr(spawned, "is_resolved", False)):
                return UndoEligibility(
                    can_undo=False,
                    action=action_row,
                    blocked_reason=BLOCK_NEXT_STAGE_ACTED,
                    blocked_by_name=_user_name(db, getattr(spawned, "resolved_by", None)),
                    blocked_at=getattr(spawned, "resolved_at", None),
                )
            if bool(getattr(spawned, "is_responded", False)):
                return UndoEligibility(
                    can_undo=False,
                    action=action_row,
                    blocked_reason=BLOCK_NEXT_STAGE_ACTED,
                    blocked_by_name=_user_name(db, getattr(spawned, "responded_by", None)),
                    blocked_at=getattr(spawned, "responded_at", None),
                )
            if getattr(spawned, "escalated_at", None) is not None:
                return UndoEligibility(
                    can_undo=False,
                    action=action_row,
                    blocked_reason=BLOCK_NEXT_STAGE_ACTED,
                    blocked_by_name=None,
                    blocked_at=getattr(spawned, "escalated_at", None),
                )
            if getattr(spawned, "handled_by_id", None) is not None:
                return UndoEligibility(
                    can_undo=False,
                    action=action_row,
                    blocked_reason=BLOCK_NEXT_STAGE_ACTED,
                    blocked_by_name=_user_name(db, getattr(spawned, "handled_by_id", None)),
                    blocked_at=getattr(spawned, "handled_at", None),
                )

    # A newer action on the same form means this one is no longer the last thing that
    # happened, and reversing it would rewrite history out of order (AC-PG-3).
    if action_row.committed_at is None:
        # Claimed but not yet stamped - the commit is still in flight. Refuse rather
        # than compare against NULL, which SQLAlchemy rejects outright.
        return UndoEligibility(
            can_undo=False, action=action_row, blocked_reason=BLOCK_STATUS_MOVED
        )
    newer = (
        db.query(SlaFormAction)
        .filter(
            SlaFormAction.source_entity_type == source_entity_type,
            SlaFormAction.source_entity_id == str(source_entity_id),
            SlaFormAction.id != action_row.id,
            SlaFormAction.committed_at.isnot(None),
            SlaFormAction.committed_at > action_row.committed_at,
        )
        .first()
    )
    if newer is not None:
        return UndoEligibility(
            can_undo=False, action=action_row, blocked_reason=BLOCK_STATUS_MOVED
        )

    return UndoEligibility(can_undo=True, action=action_row)


def _write_event(
    db: Session,
    tracker,
    event_type: str,
    reason: Optional[str],
) -> None:
    """One event-log row on the tracker, best-effort.

    The tracker table has no column that can say "voided" - `is_resolved` is the only
    terminal flag it owns - so the event log is the ONLY place the distinction between
    "somebody completed this" and "an undo swept it away" survives. Event logs also
    outlive the undo itself (FK by tracking id, cascade only on tracker delete).
    """
    from app.models.sla import ConversationSLAEventLog

    try:
        db.add(
            ConversationSLAEventLog(
                sla_tracking_id=str(tracker.id),
                event_type=event_type,
                from_tier=getattr(tracker, "current_tier", None),
                to_tier=getattr(tracker, "current_tier", None),
                event_at=datetime.utcnow(),
                reason=reason,
                assigned_to_id=getattr(tracker, "assigned_to_id", None),
                trigger="manual",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Could not write %s event log for tracker %s", event_type, tracker.id)


def void_tracker(db: Session, tracking_id: str, reason: str) -> None:
    """Take the spawned stage off its assignee's plate (AC-PGE-2).

    Resolved, not deleted: the row is history, and deleting it would take its event
    logs with it. `resolved_by` stays NULL - nobody completed this work - and a
    `voided` event log records who-adjacent context (`reason`), because the tracker
    table itself has no column that can carry the distinction.
    """
    from app.models.sla import ConversationSLATracking

    tracker = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking_id))
        .first()
    )
    if tracker is None:
        return
    tracker.is_resolved = True
    tracker.resolved_at = datetime.utcnow()
    tracker.resolved_by = None
    db.commit()
    _write_event(db, tracker, "voided", reason)


def reopen_tracker(db: Session, tracking_id: str) -> None:
    """Put the previous stage back with the person who held it (AC-PGE-3/4).

    The clock restarts from now against the stage's own hours - the original due date
    is meaningless once time has passed. `escalated_at` is deliberately left alone: a
    stage that was escalated comes back escalated and stays locked, because the handling
    lock keys on that column and not on tier.
    """
    from app.models.sla import ConversationSLATracking
    from app.services.form_sla_service import _working_due_naive

    tracker = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking_id))
        .first()
    )
    if tracker is None:
        return

    tracker.is_resolved = False
    tracker.resolved_at = None
    tracker.resolved_by = None

    # Recompute both clocks from the policy tier's HOURS. `due_at_resolution` is a
    # timestamp, not a duration - reading it as one would set the due date to an epoch
    # decades out.
    now = datetime.utcnow()
    tracker.current_tier_started_at = now
    try:
        from app.models.sla import SLAPolicyTier
        from app.services.form_sla_service import _working_clock_start_naive

        tier_row = (
            db.query(SLAPolicyTier)
            .filter(
                SLAPolicyTier.policy_id == tracker.policy_id,
                SLAPolicyTier.tier_level == tracker.current_tier,
            )
            .first()
        )
        if tier_row is not None:
            clock_start = _working_clock_start_naive(db, now)
            tracker.due_at = _working_due_naive(
                db, clock_start, float(getattr(tier_row, "response_hours", 24) or 24)
            )
            tracker.due_at_resolution = _working_due_naive(
                db, clock_start, float(getattr(tier_row, "resolution_hours", 24) or 24)
            )
    except Exception:
        # A missing tier must not block the reversal - the tracker is back with its
        # owner either way, just carrying its previous due dates.
        logger.warning("Could not recompute due dates for reopened tracker %s", tracking_id)

    db.commit()
    _write_event(db, tracker, "reopened", "restored by undo")
