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
from app.services.error_handler import (
    AppException,
    handle_conflict,
    handle_validation_error,
    handle_not_found,
)

logger = logging.getLogger(__name__)


def _now_naive() -> datetime:
    """Naive UTC 'now' to compare against the naive expires_at column."""
    return datetime.utcnow()


def coverage_role_view(
    *,
    coverer_name: Optional[str],
    covers_for_name: Optional[str],
    assigned_by_name: Optional[str],
    expires_at: Optional[datetime],
    redirect_assignments: bool,
) -> dict:
    """Role-explicit projection of a coverage row, shared by every list serializer.

    Coverage has THREE distinct people and the raw columns name them after the
    table (subscriber / target / created_by), not the role — which lets an LLM (or
    any reader) swap "covers for" with "assigned by". This returns role-named keys
    PLUS a single natural-language ``summary`` sentence built from the same facts,
    so a consumer answers any phrasing from one authoritative line instead of
    guessing which name is which. The discrete fields and the summary are generated
    together here, so they can never drift.

    Roles:
      - coverer       — handles the covered colleague's tasks while they're away
      - covers_for    — the colleague being covered (the away person)
      - assigned_by   — who set the coverage up (a HoD); None when self-subscribed
    """
    mode = "auto-assign" if redirect_assignments else "notify-only"
    coverer = coverer_name or "Someone"
    covered = covers_for_name or "a colleague"
    parts = [f"{coverer} covers for {covered}, who is away."]
    if assigned_by_name:
        parts.append(f"Assigned by {assigned_by_name}.")
    else:
        parts.append("Self-subscribed.")
    if expires_at is not None:
        parts.append(f"Active until {expires_at.strftime('%d %b %Y')} ({mode}).")
    else:
        parts.append(f"No end date ({mode}).")
    return {
        "coverer_name": coverer_name,
        "covers_for_name": covers_for_name,
        "assigned_by_name": assigned_by_name,
        "coverage_mode": mode,
        "summary": " ".join(parts),
    }


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
        # The subscriber IS the coverer here ("targets I cover"); look its name up too
        # so the role-named projection / summary can name the coverer explicitly.
        lookup_ids = {str(r.target_user_id) for r in rows}
        lookup_ids.add(str(subscriber_id))
        for r in rows:
            if getattr(r, "created_by_id", None):
                lookup_ids.add(str(r.created_by_id))
        name_by_id: dict = {}
        if lookup_ids:
            for u in self.db.query(User).filter(User.id.in_(lookup_ids)).all():
                name_by_id[str(u.id)] = (u.name or u.email or "").strip() or None
        coverer_name = name_by_id.get(str(subscriber_id))
        out = []
        for r in rows:
            created_by = str(r.created_by_id) if getattr(r, "created_by_id", None) else None
            assigned_by_name = (
                name_by_id.get(created_by)
                if created_by and created_by != str(subscriber_id)
                else None
            )
            out.append(
                {
                    "id": str(r.id),
                    "target_user_id": str(r.target_user_id),
                    "target_user_name": name_by_id.get(str(r.target_user_id)),
                    "is_active": bool(r.is_active),
                    "redirect_assignments": bool(getattr(r, "redirect_assignments", False)),
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
                    "assigned_by_hod": bool(
                        created_by and created_by != str(subscriber_id)
                    ),
                    "assigned_by_name": assigned_by_name,
                    # Role-explicit projection + natural-language summary (shared helper).
                    **coverage_role_view(
                        coverer_name=coverer_name,
                        covers_for_name=name_by_id.get(str(r.target_user_id)),
                        assigned_by_name=assigned_by_name,
                        expires_at=getattr(r, "expires_at", None),
                        redirect_assignments=bool(getattr(r, "redirect_assignments", False)),
                    ),
                }
            )
        return out

    def subscribe(
        self,
        subscriber_id: str,
        target_user_id: str,
        expires_at: Optional[datetime] = None,
        redirect_assignments: bool = False,
        created_by_id: Optional[str] = None,
    ) -> NotificationSubscription:
        """Self-service: create/reactivate a subscription where I am the coverer.

        ``redirect_assignments`` picks the mode:
        - True  = auto-assign: the target's future SLA tasks route to the subscriber
          (assignment + escalation). The subscriber must be the SOLE active coverer.
        - False = notify-only (original behaviour): coverage notification copies are
          fanned out; the subscriber takes over manually. Multiple notify-only
          coverers per target are allowed.

        Same subscriber re-subscribing the same target is an upsert (updates the mode
        + expiry), never a conflict. Scope is the SUBSCRIBER's scope-B.
        """
        subscriber_id = str(subscriber_id)
        target_user_id = str(target_user_id)
        # Target must exist and be in the subscriber's scope-B.
        target = self.db.query(User).filter(User.id == target_user_id).first()
        if not target:
            raise handle_not_found("User", target_user_id)
        if target_user_id not in self._visible_member_ids(subscriber_id):
            raise handle_validation_error(
                "You can only subscribe to users in your teams or their child teams."
            )
        return self._upsert(
            subscriber_id,
            target_user_id,
            expires_at=expires_at,
            redirect_assignments=redirect_assignments,
            created_by_id=created_by_id,
        )

    def assign_coverage(
        self,
        actor_id: str,
        coverer_id: str,
        target_user_id: str,
        expires_at: Optional[datetime] = None,
        redirect_assignments: bool = False,
    ) -> NotificationSubscription:
        """HoD action: assign ``coverer_id`` to cover ``target_user_id`` on their behalf.

        Both the coverer and the covered user must be within the ACTOR's scope-B
        (members of the actor's teams ∪ descendant teams). The caller must already
        have passed the ``notifications.coverage.manage_team`` permission gate. The
        created row records ``created_by_id = actor_id`` for audit, and the coverer is
        notified best-effort. Takes effect immediately (no accept step).
        """
        actor_id = str(actor_id)
        coverer_id = str(coverer_id)
        target_user_id = str(target_user_id)
        coverer = self.db.query(User).filter(User.id == coverer_id).first()
        if not coverer:
            raise handle_not_found("User", coverer_id)
        target = self.db.query(User).filter(User.id == target_user_id).first()
        if not target:
            raise handle_not_found("User", target_user_id)
        scope = self._visible_member_ids(actor_id)
        if coverer_id not in scope or target_user_id not in scope:
            raise handle_validation_error(
                "You can only assign coverage between users in your teams or their child teams."
            )
        sub = self._upsert(
            coverer_id,
            target_user_id,
            expires_at=expires_at,
            redirect_assignments=redirect_assignments,
            created_by_id=actor_id,
        )
        self._notify_coverer_assigned(coverer, target, expires_at, actor_id)
        return sub

    def nominate_coverer(
        self,
        target_id: str,
        coverer_id: str,
        expires_at: Optional[datetime] = None,
        redirect_assignments: bool = False,
    ) -> NotificationSubscription:
        """Self-service: I (``target_id``) nominate ``coverer_id`` to cover ME while
        I'm away. No ``manage_team`` permission required — the coverer must simply be
        in my scope-B. Mirrors :meth:`assign_coverage` with the actor covering
        themselves; the coverer is notified best-effort."""
        target_id = str(target_id)
        coverer_id = str(coverer_id)
        if coverer_id == target_id:
            raise handle_validation_error("You cannot nominate yourself as your own coverer.")
        coverer = self.db.query(User).filter(User.id == coverer_id).first()
        if not coverer:
            raise handle_not_found("User", coverer_id)
        if coverer_id not in self._visible_member_ids(target_id):
            raise handle_validation_error(
                "You can only nominate a coverer in your teams or their child teams."
            )
        sub = self._upsert(
            coverer_id,
            target_id,
            expires_at=expires_at,
            redirect_assignments=redirect_assignments,
            created_by_id=target_id,
        )
        target = self.db.query(User).filter(User.id == target_id).first()
        self._notify_coverer_assigned(coverer, target, expires_at, target_id)
        return sub

    def list_coverage_for_me(self, user_id: str) -> list[dict]:
        """Active + inactive subscriptions where I am the COVERED party (colleagues
        who cover me). Complements :meth:`list_my_subscriptions` (targets I cover)."""
        user_id = str(user_id)
        rows = (
            self.db.query(NotificationSubscription)
            .filter(NotificationSubscription.target_user_id == user_id)
            .all()
        )
        lookup_ids = {str(r.subscriber_id) for r in rows}
        lookup_ids.add(user_id)
        for r in rows:
            if getattr(r, "created_by_id", None):
                lookup_ids.add(str(r.created_by_id))
        name_by_id: dict = {}
        if lookup_ids:
            for u in self.db.query(User).filter(User.id.in_(lookup_ids)).all():
                name_by_id[str(u.id)] = (u.name or u.email or "").strip() or None
        covered_name = name_by_id.get(user_id)
        out = []
        for r in rows:
            created_by = str(r.created_by_id) if getattr(r, "created_by_id", None) else None
            # "Arranged by someone else" = a HoD set it up (created_by != the covered me).
            assigned_by_name = (
                name_by_id.get(created_by)
                if created_by and created_by != user_id
                else None
            )
            coverer_name = name_by_id.get(str(r.subscriber_id))
            out.append(
                {
                    "id": str(r.id),
                    "subscriber_id": str(r.subscriber_id),
                    "subscriber_name": coverer_name,
                    "target_user_id": user_id,
                    "target_user_name": covered_name,
                    "is_active": bool(r.is_active),
                    "redirect_assignments": bool(getattr(r, "redirect_assignments", False)),
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
                    "assigned_by_hod": bool(created_by and created_by != user_id),
                    "assigned_by_name": assigned_by_name,
                    **coverage_role_view(
                        coverer_name=coverer_name,
                        covers_for_name=covered_name,
                        assigned_by_name=assigned_by_name,
                        expires_at=getattr(r, "expires_at", None),
                        redirect_assignments=bool(getattr(r, "redirect_assignments", False)),
                    ),
                }
            )
        return out

    def _upsert(
        self,
        subscriber_id: str,
        target_user_id: str,
        *,
        expires_at: Optional[datetime] = None,
        redirect_assignments: bool = False,
        created_by_id: Optional[str] = None,
    ) -> NotificationSubscription:
        """Mode-aware exclusivity check + upsert of one (subscriber, target) row.

        Scope validation is the CALLER's responsibility (self-service uses the
        subscriber's scope; HoD assign uses the actor's). Self-coverage is rejected
        here so both entry points are covered.
        """
        subscriber_id = str(subscriber_id)
        target_user_id = str(target_user_id)
        redirect_assignments = bool(redirect_assignments)
        if subscriber_id == target_user_id:
            # Self-coverage is meaningless and would create a redirect loop.
            raise AppException(
                status_code=422,
                message="A user cannot cover for themselves.",
                code="VALIDATION_ERROR",
            )
        target = self.db.query(User).filter(User.id == target_user_id).first()
        if not target:
            raise handle_not_found("User", target_user_id)

        # Mode-aware exclusivity (other subscribers only; same-subscriber is an upsert):
        #  - redirect=ON  → reject if ANY active non-expired coverage exists for the
        #    target by a different subscriber (an auto-redirect coverer must be sole).
        #  - redirect=OFF → reject ONLY if an active redirect=ON coverage exists (can't
        #    notify-cover someone already auto-redirected); multiple notify-only OK.
        now = _now_naive()
        from sqlalchemy import or_

        others = (
            self.db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.target_user_id == target_user_id,
                NotificationSubscription.subscriber_id != subscriber_id,
                NotificationSubscription.is_active.is_(True),
                or_(
                    NotificationSubscription.expires_at.is_(None),
                    NotificationSubscription.expires_at > now,
                ),
            )
        )
        if redirect_assignments:
            conflicting = others.first()
        else:
            conflicting = others.filter(
                NotificationSubscription.redirect_assignments.is_(True)
            ).first()
        if conflicting is not None:
            covered_name = (target.name or target.email or "This colleague").strip()
            current = (
                self.db.query(User)
                .filter(User.id == str(conflicting.subscriber_id))
                .first()
            )
            current_name = (
                (current.name or current.email) if current else "another colleague"
            ) or "another colleague"
            until = (
                conflicting.expires_at.date().isoformat()
                if getattr(conflicting, "expires_at", None)
                else "further notice"
            )
            raise handle_conflict(
                f"{covered_name} is already covered by {current_name} until {until}."
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
            setattr(existing, "redirect_assignments", redirect_assignments)
            setattr(existing, "created_by_id", created_by_id)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        sub = NotificationSubscription(
            subscriber_id=subscriber_id,
            target_user_id=target_user_id,
            is_active=True,
            expires_at=expires_at,
            redirect_assignments=redirect_assignments,
            created_by_id=created_by_id,
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def _notify_coverer_assigned(
        self,
        coverer: User,
        target: User,
        expires_at: Optional[datetime],
        actor_id: str,
    ) -> None:
        """Best-effort in-app notice to the coverer that a HoD assigned them coverage."""
        try:
            from app.services.notification_service import NotificationService

            covered_name = (target.name or target.email or "a colleague").strip()
            until = (
                f" until {expires_at.date().isoformat()}"
                if expires_at is not None
                else ""
            )
            NotificationService(self.db).create_with_channel_preferences(
                user_id=str(coverer.id),
                type="coverage_assigned",
                title="You've been assigned coverage",
                body=f"You're now covering for {covered_name}{until}. Their SLA tasks may route to you.",
                data={"covered_user_id": str(target.id), "assigned_by": str(actor_id)},
                source_entity_type="coverage_assignment",
                source_entity_id=str(target.id),
                event_type="coverage_assigned",
                send_in_app=True,
                send_email=False,
                send_whatsapp=False,
                email_pref_attr="notify_email_on_assignment",
                whatsapp_pref_attr="notify_whatsapp_on_assignment",
            )
        except Exception as e:  # noqa: BLE001 — notification is best-effort
            logger.warning(
                "coverage-assigned notify to %s failed: %s", getattr(coverer, "id", "?"), e
            )

    def list_team_subscriptions(self, actor_id: str) -> list[dict]:
        """HoD view: active subscriptions where the coverer OR the covered user is in
        the actor's scope-B. Returns human-readable names (no UUIDs in the UI)."""
        actor_id = str(actor_id)
        scope = self._visible_member_ids(actor_id)
        if not scope:
            return []
        from sqlalchemy import or_

        rows = (
            self.db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.is_active.is_(True),
                or_(
                    NotificationSubscription.subscriber_id.in_(scope),
                    NotificationSubscription.target_user_id.in_(scope),
                ),
            )
            .order_by(NotificationSubscription.created_at.desc())
            .all()
        )
        ids = set()
        for r in rows:
            ids.add(str(r.subscriber_id))
            ids.add(str(r.target_user_id))
            if getattr(r, "created_by_id", None):
                ids.add(str(r.created_by_id))
        name_by_id: dict = {}
        if ids:
            for u in self.db.query(User).filter(User.id.in_(ids)).all():
                name_by_id[str(u.id)] = (u.name or u.email or "").strip() or None
        out = []
        for r in rows:
            created_by = str(r.created_by_id) if getattr(r, "created_by_id", None) else None
            # assigned_by is the HoD who set it up — only when it differs from the
            # coverer (self-subscribed rows have no assigner).
            assigned_by_name = (
                name_by_id.get(created_by)
                if created_by and created_by != str(r.subscriber_id)
                else None
            )
            out.append(
                {
                    "id": str(r.id),
                    "subscriber_id": str(r.subscriber_id),
                    "subscriber_name": name_by_id.get(str(r.subscriber_id)),
                    "target_user_id": str(r.target_user_id),
                    "target_user_name": name_by_id.get(str(r.target_user_id)),
                    "redirect_assignments": bool(getattr(r, "redirect_assignments", False)),
                    "expires_at": (
                        r.expires_at.isoformat() if getattr(r, "expires_at", None) else None
                    ),
                    "created_by_id": created_by,
                    "created_by_name": name_by_id.get(created_by) if created_by else None,
                    "assigned_by_hod": bool(created_by and created_by != str(r.subscriber_id)),
                    # Role-explicit projection + natural-language summary (shared helper):
                    # coverer = subscriber, covers_for = target, assigned_by = HoD.
                    **coverage_role_view(
                        coverer_name=name_by_id.get(str(r.subscriber_id)),
                        covers_for_name=name_by_id.get(str(r.target_user_id)),
                        assigned_by_name=assigned_by_name,
                        expires_at=getattr(r, "expires_at", None),
                        redirect_assignments=bool(getattr(r, "redirect_assignments", False)),
                    ),
                }
            )
        return out

    def deactivate_by_id(
        self, subscription_id: str, actor_id: str, can_manage: bool
    ) -> None:
        """Hard-delete a specific subscription (ADR: DELETE = hard delete).

        Allowed when the actor is the coverer (owns it), the actor is the covered
        party (cancelling cover they arranged for themselves), OR ``can_manage`` and
        both endpoints are within the actor's scope-B (HoD revoking team coverage)."""
        actor_id = str(actor_id)
        sub = (
            self.db.query(NotificationSubscription)
            .filter(NotificationSubscription.id == str(subscription_id))
            .first()
        )
        if not sub:
            raise handle_not_found("Coverage subscription", str(subscription_id))
        is_owner = str(sub.subscriber_id) == actor_id
        is_covered = str(sub.target_user_id) == actor_id
        if not (is_owner or is_covered):
            scope = self._visible_member_ids(actor_id) if can_manage else set()
            if not (
                can_manage
                and str(sub.subscriber_id) in scope
                and str(sub.target_user_id) in scope
            ):
                raise handle_not_found("Coverage subscription", str(subscription_id))
        self.db.delete(sub)
        self.db.commit()

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

    def active_coverer_for(self, target_user_id: str) -> Optional[str]:
        """Return the single active, non-expired REDIRECT coverer's user id for
        ``target_user_id`` (only ``redirect_assignments=True`` coverages auto-route).

        The redirect-mode exclusivity enforced at ``subscribe`` time guarantees ≤1
        such coverage; we still order by earliest-created and take the first
        defensively. Non-expired = ``expires_at`` is NULL OR strictly in the future
        (same convention as ``active_subscribers_for``). Notify-only coverages
        (``redirect_assignments=False``) never redirect, so they are excluded here.
        Returns None when nobody auto-covers the target.
        """
        now = _now_naive()
        from sqlalchemy import or_

        row = (
            self.db.query(NotificationSubscription.subscriber_id)
            .filter(
                NotificationSubscription.target_user_id == str(target_user_id),
                NotificationSubscription.is_active.is_(True),
                NotificationSubscription.redirect_assignments.is_(True),
                or_(
                    NotificationSubscription.expires_at.is_(None),
                    NotificationSubscription.expires_at > now,
                ),
            )
            .order_by(NotificationSubscription.created_at.asc())
            .first()
        )
        return str(row[0]) if row else None


def resolve_assignee_with_coverage(
    db: Session,
    assignee: Optional[dict],
) -> "tuple[Optional[dict], Optional[str]]":
    """Redirect a resolved SLA assignee to their active coverer, if any.

    Given an assignee dict shaped like ``{id, email, name, respond_user_id}``, if the
    assignee is currently covered (``active_coverer_for`` returns a different user),
    return ``(coverer_dict, covered_user_id)`` so the caller can route the task to the
    coverer and stamp the coverage context onto the event log. Otherwise return
    ``(assignee, None)``.

    ONE HOP: coverage is resolved exactly once — the coverer is NOT re-resolved even
    if they are themselves covered (avoids transitive chains / loops, decision 5).

    Best-effort: any lookup error degrades to ``(assignee, None)`` so routing never
    blocks on the coverage subsystem.
    """
    try:
        if not assignee or not assignee.get("id"):
            return assignee, None
        covered_id = str(assignee["id"])
        coverer_id = CoverageSubscriptionService(db).active_coverer_for(covered_id)
        if not coverer_id or str(coverer_id) == covered_id:
            return assignee, None

        coverer = db.query(User).filter(User.id == str(coverer_id)).first()
        if not coverer:
            return assignee, None

        # Reuse AccessAgentService._user_info for the canonical assignee dict shape.
        coverer_dict: Optional[dict]
        try:
            from app.services.user_service import AccessAgentService

            coverer_dict = AccessAgentService(db)._user_info(coverer)
        except Exception:  # noqa: BLE001 — fall back to a minimal dict
            coverer_dict = None
        if not coverer_dict:
            rid = getattr(coverer, "respond_user_id", None)
            coverer_dict = {
                "id": coverer.id,
                "email": coverer.email,
                "name": coverer.name or coverer.email or coverer.id,
                "respond_user_id": (str(rid).strip() if rid else None) or None,
            }
        return coverer_dict, covered_id
    except Exception as e:  # noqa: BLE001 — coverage redirect is best-effort
        logger.warning(
            "coverage redirect lookup failed for assignee %s: %s",
            (assignee or {}).get("id"),
            e,
        )
        return assignee, None


def coverage_note(db: Session, covered_user_id: Optional[str]) -> str:
    """Human-readable '(covering for <name>)' suffix for event-log reasons.

    Returns an empty string when ``covered_user_id`` is falsy. Best-effort: any
    lookup failure falls back to the raw id so the trail still records the redirect.
    """
    if not covered_user_id:
        return ""
    try:
        u = db.query(User).filter(User.id == str(covered_user_id)).first()
        name = ((u.name or u.email) if u else str(covered_user_id)) or str(
            covered_user_id
        )
    except Exception:  # noqa: BLE001
        name = str(covered_user_id)
    return f" (covering for {name})"


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
    cover_title: Optional[str] = None,
    cover_body: Optional[str] = None,
    tracking: Optional[object] = None,
    whatsapp_use_case: str = "sla_assignment",
) -> None:
    """Emit a "(covering for <Name>)" copy of an SLA assignment/escalation
    notification to every active subscriber of ``target_user_id``.

    For NOTIFY-ONLY coverage the task is assigned to the covered colleague, NOT to the
    subscriber — so callers should pass ``cover_title`` / ``cover_body`` worded as
    "assigned to <colleague>". When omitted, falls back to prefixing the assignee's text
    with "(covering for <Name>)" (legacy). When ``cover_body`` + ``tracking`` are given,
    the WhatsApp params are rebuilt PER SUBSCRIBER (recipient = the subscriber, message =
    the coverage body) so WhatsApp doesn't say "to you" either.

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
        # Coverage-correct wording when supplied (task is assigned to the colleague, not
        # to the subscriber); else legacy "(covering for X)" prefix on the assignee text.
        eff_title = cover_title or f"{title} (covering for {target_name})"
        eff_body = cover_body or f"(Covering for {target_name})\n\n{body}"
        cov_source_type = (
            f"coverage:{source_entity_type}" if source_entity_type else "coverage"
        )
        for sub_id in subscriber_ids:
            if str(sub_id) in skip:
                continue
            try:
                # Rebuild WhatsApp params for THIS subscriber + coverage body, so the
                # WhatsApp copy isn't recipient/"to you"-wrong. Falls back to the passed
                # data when we can't rebuild (no tracking / no coverage body).
                sub_data = {**(data or {}), "covering_for": target_name}
                if tracking is not None and cover_body:
                    try:
                        from app.services.form_sla_service import build_sla_whatsapp_data

                        sub_data = {
                            **sub_data,
                            **build_sla_whatsapp_data(
                                db, tracking, str(sub_id), eff_body,
                                use_case=whatsapp_use_case,
                            ),
                        }
                    except Exception:  # noqa: BLE001 — keep assignee data as fallback
                        pass
                NotificationService(db).create_with_channel_preferences(
                    user_id=str(sub_id),
                    type=notification_type,
                    title=eff_title,
                    body=eff_body,
                    data=sub_data,
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
