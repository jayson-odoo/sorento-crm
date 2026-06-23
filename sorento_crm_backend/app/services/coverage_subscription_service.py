"""Coverage subscriptions: forward-looking delegation.

A subscriber registers interest in a colleague (the target) so the target's FUTURE
SLA assignment/escalation notifications are also fanned out to the subscriber,
labelled "(covering for <Name>)". Separate from takeover (which grabs an existing
task). See PLAN-team-coverage-and-reassignment.md section G and UAC section 7.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.notification import NotificationSubscription
from app.models.user import User
from app.services.error_handler import handle_validation_error, handle_not_found

logger = logging.getLogger(__name__)


def _now_naive() -> datetime:
    """Naive UTC 'now' to compare against the naive expires_at column."""
    return datetime.utcnow()


class CoverageSubscriptionService:
    """CRUD + fan-out for notification (coverage) subscriptions."""

    def __init__(self, db: Session):
        self.db = db

    # ----- scope helpers -----------------------------------------------------
    def _visible_member_ids(self, user_id: str) -> set:
        """Scope-B: users in my teams ∪ descendant teams (the coverage picker scope
        and the team-tasks visibility scope)."""
        from app.models.access import TeamMember
        from app.services.user_service import descendant_team_ids

        my_team_ids = {
            str(tid)
            for (tid,) in self.db.query(TeamMember.team_id)
            .filter(TeamMember.user_id == str(user_id))
            .all()
        }
        if not my_team_ids:
            return set()
        visible_team_ids = descendant_team_ids(self.db, my_team_ids)
        if not visible_team_ids:
            return set()
        return {
            str(uid)
            for (uid,) in self.db.query(TeamMember.user_id)
            .filter(TeamMember.team_id.in_(visible_team_ids))
            .all()
        }

    # ----- CRUD --------------------------------------------------------------
    def list_my_subscriptions(self, subscriber_id: str) -> list[dict]:
        """Active + inactive subscriptions where I am the subscriber (targets I cover)."""
        rows = (
            self.db.query(NotificationSubscription)
            .filter(NotificationSubscription.subscriber_id == str(subscriber_id))
            .all()
        )
        target_ids = {str(r.target_user_id) for r in rows}
        name_by_id: dict = {}
        if target_ids:
            for u in self.db.query(User).filter(User.id.in_(target_ids)).all():
                name_by_id[str(u.id)] = (u.name or u.email or "").strip() or None
        return [
            {
                "id": str(r.id),
                "target_user_id": str(r.target_user_id),
                "target_user_name": name_by_id.get(str(r.target_user_id)),
                "is_active": bool(r.is_active),
                "expires_at": (
                    getattr(r, "expires_at").isoformat()
                    if getattr(r, "expires_at", None)
                    else None
                ),
                "created_at": (
                    getattr(r, "created_at").isoformat()
                    if getattr(r, "created_at", None)
                    else None
                ),
            }
            for r in rows
        ]

    def subscribe(
        self,
        subscriber_id: str,
        target_user_id: str,
        expires_at: Optional[datetime] = None,
    ) -> NotificationSubscription:
        """Create/reactivate an active subscription (subscriber → target)."""
        subscriber_id = str(subscriber_id)
        target_user_id = str(target_user_id)
        if subscriber_id == target_user_id:
            raise handle_validation_error("You cannot subscribe to your own notifications.")
        # Target must exist and be in scope-B.
        target = self.db.query(User).filter(User.id == target_user_id).first()
        if not target:
            raise handle_not_found("User", target_user_id)
        if target_user_id not in self._visible_member_ids(subscriber_id):
            raise handle_validation_error(
                "You can only subscribe to users in your teams or their child teams."
            )
        existing = (
            self.db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.subscriber_id == subscriber_id,
                NotificationSubscription.target_user_id == target_user_id,
            )
            .first()
        )
        if existing:
            setattr(existing, "is_active", True)
            setattr(existing, "expires_at", expires_at)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        sub = NotificationSubscription(
            subscriber_id=subscriber_id,
            target_user_id=target_user_id,
            is_active=True,
            expires_at=expires_at,
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def unsubscribe(self, subscriber_id: str, target_user_id: str) -> None:
        """Hard-delete the (subscriber, target) subscription (ADR: DELETE = hard delete).

        The user no longer covers this colleague, so the row is removed entirely —
        it must not linger in the list as an "Inactive" row. Re-subscribing simply
        creates a fresh row; natural expiry still soft-deactivates via
        ``deactivate_expired_subscriptions``.
        """
        sub = (
            self.db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.subscriber_id == str(subscriber_id),
                NotificationSubscription.target_user_id == str(target_user_id),
            )
            .first()
        )
        if not sub:
            raise handle_not_found("Coverage subscription", f"{subscriber_id}/{target_user_id}")
        self.db.delete(sub)
        self.db.commit()

    # ----- expiry ------------------------------------------------------------
    def deactivate_expired_subscriptions(self) -> int:
        """Deactivate active subscriptions whose expires_at has passed. Returns count."""
        now = _now_naive()
        rows = (
            self.db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.is_active.is_(True),
                NotificationSubscription.expires_at.isnot(None),
                NotificationSubscription.expires_at <= now,
            )
            .all()
        )
        for r in rows:
            setattr(r, "is_active", False)
        if rows:
            self.db.commit()
        return len(rows)

    # ----- fan-out -----------------------------------------------------------
    def active_subscribers_for(self, target_user_id: str) -> list[str]:
        """Active, non-expired subscriber ids covering ``target_user_id``."""
        now = _now_naive()
        from sqlalchemy import or_

        rows = (
            self.db.query(NotificationSubscription.subscriber_id)
            .filter(
                NotificationSubscription.target_user_id == str(target_user_id),
                NotificationSubscription.is_active.is_(True),
                or_(
                    NotificationSubscription.expires_at.is_(None),
                    NotificationSubscription.expires_at > now,
                ),
            )
            .all()
        )
        return [str(r[0]) for r in rows]


def fan_out_coverage_copies(
    db: Session,
    *,
    target_user_id: str,
    actor_user_id: Optional[str],
    notification_type: str,
    title: str,
    body: str,
    data: Optional[dict],
    source_entity_type: Optional[str],
    source_entity_id: Optional[str],
    event_type: Optional[str],
    email_pref_attr: str,
    whatsapp_pref_attr: str,
    send_whatsapp: bool = True,
) -> None:
    """Emit a "(covering for <Name>)" copy of an SLA assignment/escalation
    notification to every active subscriber of ``target_user_id``.

    - In-app always; email/WhatsApp gated by the SUBSCRIBER's own per-event toggles.
    - Deduped: skips the actual assignee (``target_user_id``) and the actor — if the
      subscriber already gets the notification directly, no double-send (AC-CS-6).
    - Best-effort: never raises (the primary notification already committed).
    - Distinct source_entity_type prefix ('coverage:') so the per-(user,source,event)
      idempotency in create_with_channel_preferences never collides with the
      subscriber's own direct notifications for the same tracker.
    """
    try:
        from app.services.notification_service import NotificationService

        svc = CoverageSubscriptionService(db)
        subscriber_ids = svc.active_subscribers_for(target_user_id)
        if not subscriber_ids:
            return
        target = db.query(User).filter(User.id == str(target_user_id)).first()
        target_name = (
            (target.name or target.email) if target else str(target_user_id)
        ) or "a teammate"
        skip = {str(target_user_id)}
        if actor_user_id:
            skip.add(str(actor_user_id))
        cover_title = f"{title} (covering for {target_name})"
        cover_body = f"(Covering for {target_name})\n\n{body}"
        cov_source_type = (
            f"coverage:{source_entity_type}" if source_entity_type else "coverage"
        )
        for sub_id in subscriber_ids:
            if str(sub_id) in skip:
                continue
            try:
                NotificationService(db).create_with_channel_preferences(
                    user_id=str(sub_id),
                    type=notification_type,
                    title=cover_title,
                    body=cover_body,
                    data={**(data or {}), "covering_for": target_name},
                    source_entity_type=cov_source_type,
                    source_entity_id=source_entity_id,
                    event_type=event_type,
                    send_in_app=True,
                    send_email=True,
                    send_whatsapp=send_whatsapp,
                    email_pref_attr=email_pref_attr,
                    whatsapp_pref_attr=whatsapp_pref_attr,
                )
            except Exception as e:  # noqa: BLE001 — per-subscriber best-effort
                logger.warning(
                    "coverage fan-out to %s for target %s failed: %s",
                    sub_id,
                    target_user_id,
                    e,
                )
    except Exception as e:  # noqa: BLE001 — fan-out is best-effort
        logger.warning("coverage fan-out failed for target %s: %s", target_user_id, e)
