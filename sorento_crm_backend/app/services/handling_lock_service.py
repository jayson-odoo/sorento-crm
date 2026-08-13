"""Form handling-lock ("I'm handling this") — claim / take-over / release + CTA guard.

Once a FORM SLA tracker escalates (``escalated_at`` is set — NOT ``current_tier > 1``,
since a config may START above tier 1, e.g. project_sales begins at tier 2) and the
per-form flag is on,
every state-changing business CTA (approve/reject/process/close/submit/reopen) is
disabled for everyone until an eligible team-chain member claims the lock
(``ConversationSLATracking.handled_by_id``). The lock is mutually exclusive and
SEPARATE from ``assigned_to_id`` — claiming never reassigns and never de-escalates.

Scope: FORM SLA rows only (``source_entity_type in FORM_SLA_TYPES``). n8n
conversation-SLA rows sharing the table are never touched.

See docs/plans/PLAN-form-handling-lock.md (§4, §6, §8).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.access import TeamMember
from app.models.sla import (
    ConversationSLATracking,
    HANDLING_CLAIMED,
    HANDLING_RELEASED,
    HANDLING_TAKEN_OVER,
)
from app.models.user import SystemSetting, User
from app.services.error_handler import AppException
from app.services.form_sla_service import FORM_SLA_TYPES
from app.services.sla_scope import open_tracker_scope

logger = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Feature flag                                                                 #
# --------------------------------------------------------------------------- #
def is_handling_lock_enabled(db: Session, source_entity_type: Optional[str]) -> bool:
    """Whether the handling lock is enabled for ``source_entity_type``.

    Reads the singleton ``system_settings.handling_lock_enabled_types`` (CSV). The
    singleton is DB-enforced (migration 253), so ``.first()`` is deterministic —
    mirrors every other SystemSetting reader.
    """
    if not source_entity_type:
        return False
    try:
        row = db.query(SystemSetting).first()
    except Exception:  # noqa: BLE001 — partial schema / bad session.
        # Treat a settings-read blip as "lock disabled" (returns False → the CTA
        # guard allows the action): an added restriction must not hard-block every
        # locked CTA on a transient DB error. This is deliberately fail-OPEN.
        db.rollback()
        return False
    if not row:
        return False
    raw = str(getattr(row, "handling_lock_enabled_types", "") or "")
    enabled = {t.strip() for t in raw.split(",") if t.strip()}
    return str(source_entity_type) in enabled


# --------------------------------------------------------------------------- #
# Eligibility                                                                  #
# --------------------------------------------------------------------------- #
def eligible_user_ids(db: Session, tracker: ConversationSLATracking) -> set[str]:
    """User ids in the tracker's escalation team-chain (agent + team_set_code, tiers
    1..current_tier). Membership defines who may claim/take-over — the same chain the
    escalation round-robin draws from."""
    agent_id = str(tracker.agent_id) if tracker.agent_id is not None else None
    if not agent_id:
        return set()
    from app.services.user_service import AccessAgentService

    from app.services.sla_service import _tracking_company_id

    svc = AccessAgentService(db)
    current = int(getattr(tracker, "current_tier", 1) or 1)
    company_id = _tracking_company_id(tracker)
    team_ids: list[str] = []
    for tier in range(1, current + 1):
        team_id = svc.get_team_id_by_tier(
            agent_id, tier, team_set_code=tracker.team_set_code, company_id=company_id
        )
        if team_id:
            team_ids.append(team_id)
    if not team_ids:
        return set()
    rows = (
        db.query(TeamMember.user_id)
        .filter(TeamMember.team_id.in_(team_ids))
        .all()
    )
    return {str(r[0]) for r in rows if r[0]}


def _is_eligible(db: Session, tracker: ConversationSLATracking, user_id: str) -> bool:
    return str(user_id) in eligible_user_ids(db, tracker)


def _is_escalated(tracker: ConversationSLATracking) -> bool:
    """A form tracker is ESCALATED once ``escalated_at`` is stamped by ``_escalate_tracker``.

    NOT ``current_tier > 1``: some configs start above tier 1 (project_sales begins at
    tier 2 with no tier 1 team), so a fresh, never-escalated tracker can sit at tier 2.
    ``escalated_at`` is set ONLY on a real escalation and never on initial assignment —
    the same signal the SLA-escalation banner keys on (``escalation_reason``).
    """
    return getattr(tracker, "escalated_at", None) is not None


def _user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == str(user_id)).first()
    return (u.name or u.email) if u else None


def _actor_is_admin(db: Session, user_id: str) -> bool:
    from app.services.user_service import UserPermissionService

    slugs = UserPermissionService(db).get_user_role_slugs(str(user_id))
    return bool(slugs & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"})


# --------------------------------------------------------------------------- #
# CTA guard                                                                    #
# --------------------------------------------------------------------------- #
def _active_form_tracker(
    db: Session,
    source_entity_id: str,
    source_entity_type: Optional[str] = None,
) -> Optional[ConversationSLATracking]:
    """Newest unresolved FORM tracker for a form row. Scope-limited to FORM_SLA_TYPES,
    so conversation-SLA rows can never match."""
    q = db.query(ConversationSLATracking).filter(
        ConversationSLATracking.source_entity_id == str(source_entity_id),
        # A stage voided by a contact revision is not active - the lock banner must
        # follow the restarted stage, not the cancelled one.
        *open_tracker_scope(),
        ConversationSLATracking.source_entity_type.in_(FORM_SLA_TYPES),
    )
    if source_entity_type:
        q = q.filter(ConversationSLATracking.source_entity_type == source_entity_type)
    return q.order_by(ConversationSLATracking.initiated_at.desc()).first()


def assert_can_act_on_form(
    db: Session,
    source_entity_id: str,
    actor: dict,
    *,
    source_entity_type: Optional[str] = None,
) -> None:
    """Handling-lock gate for a state-changing business CTA. Allows the action when:
    flag off for the type, OR no active form tracker, OR tracker not escalated. Once
    escalated + flag on, only the lock holder (or an admin/superadmin on an UNCLAIMED
    tracker) may act — everyone else gets a 403.
    """
    tracker = _active_form_tracker(db, source_entity_id, source_entity_type)
    if tracker is None:
        return  # no active form tracker -> today's behavior
    if not _is_escalated(tracker):
        return  # not escalated -> no lock
    if not is_handling_lock_enabled(db, tracker.source_entity_type):
        return  # flag off -> today's behavior

    actor_id = str((actor or {}).get("id") or "")
    handler = tracker.handled_by_id
    if handler and str(handler) == actor_id:
        return  # the lock holder
    if not handler and actor_id and _actor_is_admin(db, actor_id):
        return  # admin/superadmin may act while unclaimed only

    if handler:
        holder = _user_name(db, handler) or "another user"
        message = f"This form is being handled by {holder}. Take over to act."
    else:
        message = "This form is escalated. Claim it before you can act."
    raise AppException(status_code=403, message=message, code="FORBIDDEN")


# --------------------------------------------------------------------------- #
# Claim / take-over / release                                                  #
# --------------------------------------------------------------------------- #
class HandlingLockService:
    """Claim / take-over / release the handling lock on a form SLA tracker."""

    def __init__(self, db: Session):
        self.db = db

    # -- helpers ----------------------------------------------------------- #
    def _load_form_tracker(self, tracking_id: str) -> ConversationSLATracking:
        tracker = (
            self.db.query(ConversationSLATracking)
            .filter(ConversationSLATracking.id == str(tracking_id))
            .first()
        )
        if tracker is None:
            raise AppException(
                status_code=404, message="SLA tracking not found.", code="NOT_FOUND"
            )
        if str(tracker.source_entity_type or "") not in FORM_SLA_TYPES:
            # Scope boundary — never operate on a conversation-SLA row.
            raise AppException(
                status_code=422,
                message="This tracking row is not a form SLA stage.",
                code="VALIDATION_ERROR",
            )
        return tracker

    def _assert_claimable(self, tracker: ConversationSLATracking, actor_id: str) -> None:
        if not is_handling_lock_enabled(self.db, tracker.source_entity_type):
            raise AppException(
                status_code=422,
                message="The handling lock is not enabled for this form type.",
                code="VALIDATION_ERROR",
            )
        if bool(tracker.is_resolved):
            raise AppException(
                status_code=422,
                message="This SLA task is already resolved.",
                code="VALIDATION_ERROR",
            )
        if not _is_escalated(tracker):
            raise AppException(
                status_code=422,
                message="This form is not escalated; the handling lock does not apply.",
                code="VALIDATION_ERROR",
            )
        if not _is_eligible(self.db, tracker, actor_id):
            raise AppException(
                status_code=403,
                message="Only a member of the escalation team can handle this form.",
                code="FORBIDDEN",
            )

    def _write_event_log(
        self,
        tracker: ConversationSLATracking,
        *,
        event_type: str,
        actor_id: str,
        handler_id: Optional[str],
        reason: str,
    ) -> None:
        """Best-effort: mirror FormSLAOrchestrator._write_event_log (naive-UTC safe)."""
        from app.services.form_sla_service import FormSLAOrchestrator

        FormSLAOrchestrator(self.db)._write_event_log(
            tracker_id=str(tracker.id),
            event_type=event_type,
            from_tier=int(getattr(tracker, "current_tier", 0) or 0) or None,
            to_tier=int(getattr(tracker, "current_tier", 0) or 0) or None,
            reason=reason,
            assigned_to_id=handler_id,
            trigger="manual",
            triggered_by_id=actor_id,
        )

    def _notify(
        self,
        tracker: ConversationSLATracking,
        *,
        kind: str,
        actor_id: str,
        handler_id: Optional[str],
        recipients: set[str],
    ) -> None:
        """Best-effort notify (never raises). ``kind`` in {claimed, taken_over, released}.
        Recipients already exclude the actor (§6: affected parties minus the actor)."""
        recipients = {str(r) for r in recipients if r and str(r) != str(actor_id)}
        if not recipients:
            return
        try:
            from app.services.form_sla_service import (
                _full_form_link,
                _resolve_entity_number,
                build_sla_whatsapp_data,
            )
            from app.services.notification_service import NotificationService

            s_type = str(tracker.source_entity_type or "")
            s_id = str(tracker.source_entity_id or "")
            link = _full_form_link(s_type, s_id)
            type_label = (s_type or "form").replace("_", " ")
            number = _resolve_entity_number(self.db, s_type, s_id) or type_label.capitalize()
            handler_name = _user_name(self.db, handler_id or actor_id) or "A teammate"

            if kind == "claimed":
                title = f"Handling started: {number}"
                body = f"{handler_name} is now handling {type_label} {number}."
            elif kind == "taken_over":
                title = f"Handling taken over: {number}"
                body = f"{handler_name} took over handling {type_label} {number} from you."
            else:  # released
                title = f"Handling released: {number}"
                body = (
                    f"{handler_name} released handling of {type_label} {number}. "
                    f"It is open to handle again."
                )
            body += f"\n\nOpen: {link}"
            use_case = f"sla_handling_{kind}"

            svc = NotificationService(self.db)
            for uid in recipients:
                data = {
                    "tracking_id": str(tracker.id),
                    "source_entity_type": tracker.source_entity_type,
                    "source_entity_id": tracker.source_entity_id,
                    "link": link,
                    **build_sla_whatsapp_data(
                        self.db,
                        tracker,
                        uid,
                        body,
                        use_case=use_case,
                        extra_vars={"handler_name": handler_name},
                    ),
                }
                try:
                    svc.create_with_channel_preferences(
                        user_id=uid,
                        type="form_sla",
                        title=title,
                        body=body,
                        data=data,
                        source_entity_type="form_sla_tracking",
                        source_entity_id=str(tracker.id),
                        # No dedup key: successive claim/release on the same tracker
                        # must each notify (event_type left None skips the guard).
                        event_type=None,
                        send_in_app=True,
                        send_email=True,
                        send_web_push=False,
                        send_whatsapp=True,
                        whatsapp_pref_attr="notify_whatsapp_on_handling",
                        email_pref_attr="notify_email_on_handling",
                    )
                except Exception as e:  # noqa: BLE001 — one bad recipient must not block others
                    logger.warning(
                        "Handling notify failed for tracker %s -> user %s: %s",
                        tracker.id,
                        uid,
                        e,
                    )
        except Exception as e:  # noqa: BLE001 — post-commit side effect is best-effort
            logger.warning(
                "Handling notify fan-out failed for tracker %s: %s", tracker.id, e
            )

    # -- public API -------------------------------------------------------- #
    def claim_handling(
        self, tracking_id: str, actor: dict
    ) -> ConversationSLATracking:
        actor_id = str((actor or {}).get("id") or "")
        tracker = self._load_form_tracker(tracking_id)
        self._assert_claimable(tracker, actor_id)

        now = _utc_naive_now()
        # Atomic claim: only succeeds while unclaimed. A concurrent second claim finds
        # 0 rows -> 409 (no double-claim race).
        res = self.db.execute(
            update(ConversationSLATracking)
            .where(
                ConversationSLATracking.id == str(tracker.id),
                ConversationSLATracking.handled_by_id.is_(None),
            )
            .values(handled_by_id=actor_id, handled_at=now)
        )
        self.db.commit()
        if res.rowcount == 0:
            self.db.refresh(tracker)
            holder = _user_name(self.db, tracker.handled_by_id) or "another user"
            raise AppException(
                status_code=409,
                message=f"This form is already being handled by {holder}.",
                code="CONFLICT",
            )
        self.db.refresh(tracker)

        recipients = eligible_user_ids(self.db, tracker)
        if tracker.assigned_to_id:
            recipients.add(str(tracker.assigned_to_id))
        self._write_event_log(
            tracker,
            event_type=HANDLING_CLAIMED,
            actor_id=actor_id,
            handler_id=actor_id,
            reason="Claimed handling",
        )
        self._notify(
            tracker,
            kind="claimed",
            actor_id=actor_id,
            handler_id=actor_id,
            recipients=recipients,
        )
        return tracker

    def take_over_handling(
        self, tracking_id: str, actor: dict, expected_handler_id: Optional[str]
    ) -> ConversationSLATracking:
        actor_id = str((actor or {}).get("id") or "")
        tracker = self._load_form_tracker(tracking_id)
        self._assert_claimable(tracker, actor_id)

        expected = str(expected_handler_id) if expected_handler_id else None
        if expected is None:
            # Take-over requires an existing holder; an unclaimed tracker is a claim.
            raise AppException(
                status_code=409,
                message="This form is not currently being handled. Refresh — you may claim it instead.",
                code="CONFLICT",
            )
        now = _utc_naive_now()
        # Optimistic take-over: only succeeds while the current holder still matches the
        # client's expected value (409 on mismatch — no double take-over).
        res = self.db.execute(
            update(ConversationSLATracking)
            .where(
                ConversationSLATracking.id == str(tracker.id),
                ConversationSLATracking.handled_by_id == expected,
            )
            .values(handled_by_id=actor_id, handled_at=now)
        )
        self.db.commit()
        if res.rowcount == 0:
            self.db.refresh(tracker)
            holder = _user_name(self.db, tracker.handled_by_id) or "someone else"
            raise AppException(
                status_code=409,
                message=(
                    f"Handling has changed — it is now held by {holder}. Refresh and retry."
                ),
                code="CONFLICT",
            )
        self.db.refresh(tracker)
        setattr(tracker, "_previous_handler_id", expected)

        self._write_event_log(
            tracker,
            event_type=HANDLING_TAKEN_OVER,
            actor_id=actor_id,
            handler_id=actor_id,
            reason=f"Took over handling from {expected or 'unassigned'}",
        )
        # Notify the displaced holder only.
        self._notify(
            tracker,
            kind="taken_over",
            actor_id=actor_id,
            handler_id=actor_id,
            recipients={expected} if expected else set(),
        )
        return tracker

    def release_handling(
        self, tracking_id: str, actor: dict
    ) -> ConversationSLATracking:
        actor_id = str((actor or {}).get("id") or "")
        tracker = self._load_form_tracker(tracking_id)
        if str(tracker.handled_by_id or "") != actor_id:
            raise AppException(
                status_code=403,
                message="Only the current handler can release this form.",
                code="FORBIDDEN",
            )

        # Recipients captured BEFORE clearing the lock.
        recipients = eligible_user_ids(self.db, tracker)
        res = self.db.execute(
            update(ConversationSLATracking)
            .where(
                ConversationSLATracking.id == str(tracker.id),
                ConversationSLATracking.handled_by_id == actor_id,
            )
            .values(handled_by_id=None, handled_at=None)
        )
        self.db.commit()
        if res.rowcount == 0:
            self.db.refresh(tracker)
            raise AppException(
                status_code=409,
                message="Handling has already changed. Refresh and retry.",
                code="CONFLICT",
            )
        self.db.refresh(tracker)

        self._write_event_log(
            tracker,
            event_type=HANDLING_RELEASED,
            actor_id=actor_id,
            handler_id=None,
            reason="Released handling",
        )
        self._notify(
            tracker,
            kind="released",
            actor_id=actor_id,
            handler_id=actor_id,
            recipients=recipients,
        )
        return tracker
