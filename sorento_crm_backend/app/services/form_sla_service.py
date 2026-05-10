"""Form SLA orchestrator: starts/responds/resolves SLA trackers for forms.

Forms supported (source_entity_type values): stock_inquiry, purchase_request,
sponsorship_form, complaint. Configuration lives in form_sla_configs and is
queried by source_entity_type. Trackers themselves reuse conversation_sla_tracking
(same table) — a tracker for a form has source_entity_type set to the form's
type, source_entity_id set to the form row's id.

A single emit_event() call is dropped at every form-service state transition;
the orchestrator decides whether to start/respond/resolve based on the
configured event names. Multi-stage chains spawn the next stage on resolve.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import AccessAgent
from app.models.notification import Notification
from app.models.sla import (
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicyTier,
)
from app.services.error_handler import handle_validation_error
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


FORM_SLA_TYPES = (
    "stock_inquiry",
    "purchase_request",
    "sponsorship_form",
    "complaint",
    "ticket",
)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _form_detail_link(source_entity_type: str, source_entity_id: str) -> str:
    """Build a frontend deep link for the form's detail page (consumed by notification UI)."""
    if source_entity_type == "stock_inquiry":
        return f"/procurement-management/stock-inquiries/{source_entity_id}"
    if source_entity_type in ("purchase_request", "sponsorship_form"):
        return f"/procurement-management/purchase-requests/{source_entity_id}"
    if source_entity_type == "complaint":
        return f"/complaint-management/complaints/{source_entity_id}"
    if source_entity_type == "ticket":
        return f"/ticket-management/tickets/{source_entity_id}"
    return f"/{source_entity_type.replace('_', '-')}/{source_entity_id}"


class FormSLAOrchestrator:
    """Single funnel for form-service transitions to drive SLA trackers."""

    def __init__(self, db: Session):
        self.db = db

    # ---------------- public API ----------------

    def emit_event(
        self,
        source_entity_type: str,
        source_entity_id: str,
        event_name: str,
        *,
        contact_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        """Evaluate every active config for this form type and dispatch matching action.

        Errors are logged but never propagated — SLA orchestration must not block
        the underlying state transition.
        """
        if not source_entity_type or not source_entity_id or not event_name:
            return

        try:
            configs = (
                self.db.query(FormSLAConfig)
                .filter(
                    FormSLAConfig.source_entity_type == source_entity_type,
                    FormSLAConfig.is_active.is_(True),
                )
                .all()
            )
        except Exception as e:
            # Table may not exist yet (migrations behind) or session may be in a bad
            # state from a prior op — roll back so the parent transaction can keep
            # using this session for subsequent reads/writes.
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(
                "Form SLA config lookup failed for %s; skipping SLA emit: %s",
                source_entity_type,
                e,
            )
            return
        if not configs:
            return

        def _matches(field: Optional[str]) -> bool:
            if not field:
                return False
            for token in str(field).split(","):
                if token.strip() == event_name:
                    return True
            return False

        for config in configs:
            try:
                if _matches(config.start_event):
                    self._start_for_config(
                        config, source_entity_id, contact_id=contact_id
                    )
                if _matches(config.respond_event):
                    self._respond_for_active(
                        config, source_entity_id, actor_user_id=actor_user_id
                    )
                if _matches(config.resolve_event):
                    self._resolve_for_active(
                        config,
                        source_entity_id,
                        actor_user_id=actor_user_id,
                        contact_id=contact_id,
                    )
            except Exception as e:
                logger.warning(
                    "Form SLA event '%s' on %s/%s for config %s failed: %s",
                    event_name,
                    source_entity_type,
                    source_entity_id,
                    config.id,
                    e,
                )

    def trackers_for_source(
        self,
        source_entity_type: str,
        source_entity_id: str,
    ) -> list[ConversationSLATracking]:
        """All trackers (active + closed) for one form row, ordered oldest first."""
        return (
            self.db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == source_entity_type,
                ConversationSLATracking.source_entity_id == str(source_entity_id),
            )
            .order_by(ConversationSLATracking.initiated_at.asc())
            .all()
        )

    def scan_overdue_and_escalate(self) -> dict:
        """Find form trackers past due + not escalated this tier, escalate to next tier."""
        from app.services.user_service import AccessAgentService

        now = _utc_naive_now()
        candidates = (
            self.db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.is_resolved.is_(False),
                ConversationSLATracking.source_entity_type.in_(FORM_SLA_TYPES),
            )
            .all()
        )
        escalated_count = 0
        skipped_count = 0
        for tracker in candidates:
            try:
                due = tracker.due_at
                due_resolution = tracker.due_at_resolution
                overdue = (due is not None and due < now) or (
                    due_resolution is not None and due_resolution < now
                )
                if not overdue:
                    continue
                # idempotency: skip if already escalated since current tier started
                if (
                    tracker.escalated_at is not None
                    and tracker.current_tier_started_at is not None
                    and tracker.escalated_at >= tracker.current_tier_started_at
                ):
                    skipped_count += 1
                    continue

                target_tier = int(tracker.current_tier or 1) + 1
                next_tier = (
                    self.db.query(SLAPolicyTier)
                    .filter(
                        SLAPolicyTier.policy_id == tracker.policy_id,
                        SLAPolicyTier.tier_level == target_tier,
                    )
                    .first()
                )
                if not next_tier:
                    skipped_count += 1
                    continue

                # resolve next-tier assignee via access agents (round-robin)
                agent_id = (
                    str(tracker.agent_id) if tracker.agent_id is not None else None
                )
                if not agent_id:
                    logger.warning(
                        "Tracker %s has no agent_id; cannot escalate", tracker.id
                    )
                    skipped_count += 1
                    continue
                agent_svc = AccessAgentService(self.db)
                team_id = agent_svc.get_team_id_by_tier(
                    agent_id,
                    target_tier,
                    team_set_code=tracker.team_set_code,
                )
                if not team_id:
                    skipped_count += 1
                    continue
                assignee = agent_svc.get_next_assignee(agent_id, team_id)
                if not assignee:
                    skipped_count += 1
                    continue

                response_hrs = float(getattr(next_tier, "response_hours", 24) or 24)
                resolution_hrs = float(
                    getattr(next_tier, "resolution_hours", 24) or 24
                )
                tracker.current_tier = target_tier
                tracker.current_tier_started_at = now
                tracker.escalated_at = now
                tracker.escalation_reason = "Response/resolution overdue"
                tracker.due_at = now + timedelta(hours=response_hrs)
                tracker.due_at_resolution = now + timedelta(hours=resolution_hrs)
                tracker.assigned_to_id = assignee["id"]
                tracker.assigned_to = (
                    str(assignee.get("respond_user_id"))
                    if assignee.get("respond_user_id")
                    else None
                )
                self.db.flush()

                # event log + notification
                self._write_event_log(
                    tracker_id=str(tracker.id),
                    event_type="escalation",
                    from_tier=target_tier - 1,
                    to_tier=target_tier,
                    reason="Response/resolution overdue",
                    assigned_to_id=assignee["id"],
                    due_at=tracker.due_at,
                )
                self._notify_assignee(
                    tracker,
                    kind="escalated",
                    reason="Response or resolution overdue",
                )
                escalated_count += 1
            except Exception as e:
                logger.exception(
                    "Form SLA escalation failed for tracker %s: %s", tracker.id, e
                )

        if escalated_count:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.exception("Commit failed after form SLA escalation: %s", e)

        return {
            "scanned": len(candidates),
            "escalated": escalated_count,
            "skipped": skipped_count,
        }

    # ---------------- internals ----------------

    def _active_tracker(
        self, config: FormSLAConfig, source_entity_id: str
    ) -> Optional[ConversationSLATracking]:
        return (
            self.db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == config.source_entity_type,
                ConversationSLATracking.source_entity_id == str(source_entity_id),
                ConversationSLATracking.policy_id == config.policy_id,
                ConversationSLATracking.is_resolved.is_(False),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )

    def _start_for_config(
        self,
        config: FormSLAConfig,
        source_entity_id: str,
        *,
        contact_id: Optional[str] = None,
    ) -> Optional[ConversationSLATracking]:
        """Idempotent: skip if active tracker for this stage already exists."""
        from app.services.user_service import AccessAgentService

        existing = self._active_tracker(config, source_entity_id)
        if existing:
            return existing

        agent = (
            self.db.query(AccessAgent)
            .filter(AccessAgent.code == config.agent_code)
            .first()
        )
        if not agent:
            raise handle_validation_error(
                f"No access agent with code '{config.agent_code}' for form SLA config {config.id}."
            )
        agent_svc = AccessAgentService(self.db)
        team_id = agent_svc.get_team_id_by_tier(
            str(agent.id),
            1,
            team_set_code=config.team_set_code,
        )
        if not team_id:
            raise handle_validation_error(
                f"Agent '{config.agent_code}' has no tier 1 team"
                + (
                    f" in set '{config.team_set_code}'"
                    if config.team_set_code
                    else ""
                )
                + ". Configure tier 1 before activating this SLA config."
            )
        assignee = agent_svc.get_next_assignee(str(agent.id), team_id)
        if not assignee:
            raise handle_validation_error(
                f"No members in tier 1 team for agent '{config.agent_code}'."
            )

        tier1 = (
            self.db.query(SLAPolicyTier)
            .filter(
                SLAPolicyTier.policy_id == config.policy_id,
                SLAPolicyTier.tier_level == 1,
            )
            .first()
        )
        if not tier1:
            raise handle_validation_error(
                f"SLA policy {config.policy_id} has no tier 1; cannot start tracker."
            )

        now = _utc_naive_now()
        response_hrs = float(getattr(tier1, "response_hours", 24) or 24)
        resolution_hrs = float(getattr(tier1, "resolution_hours", 24) or 24)
        tracker = ConversationSLATracking(
            policy_id=config.policy_id,
            current_tier=1,
            assigned_to=(
                str(assignee.get("respond_user_id"))
                if assignee.get("respond_user_id")
                else None
            ),
            assigned_to_id=assignee["id"],
            initiated_at=now,
            current_tier_started_at=now,
            due_at=now + timedelta(hours=response_hrs),
            due_at_resolution=now + timedelta(hours=resolution_hrs),
            is_responded=False,
            is_resolved=False,
            respond_contact_id=contact_id,
            source_entity_type=config.source_entity_type,
            source_entity_id=str(source_entity_id),
            agent_id=str(agent.id),
            team_set_code=config.team_set_code,
        )
        self.db.add(tracker)
        self.db.commit()
        self.db.refresh(tracker)

        self._notify_assignee(tracker, kind="assigned")
        return tracker

    def _respond_for_active(
        self,
        config: FormSLAConfig,
        source_entity_id: str,
        *,
        actor_user_id: Optional[str] = None,
    ) -> None:
        from app.schemas.sla import ConversationSLATrackingUpdate
        from app.services.sla_service import ConversationSLATrackingService

        tracker = self._active_tracker(config, source_entity_id)
        if not tracker or bool(getattr(tracker, "is_responded", False)):
            return
        svc = ConversationSLATrackingService(self.db)
        update_payload = {"is_responded": True}
        if actor_user_id:
            update_payload["responded_by"] = actor_user_id
        svc.update_tracking(
            str(tracker.id),
            ConversationSLATrackingUpdate(**update_payload),
        )

    def _resolve_for_active(
        self,
        config: FormSLAConfig,
        source_entity_id: str,
        *,
        actor_user_id: Optional[str] = None,
        contact_id: Optional[str] = None,
    ) -> None:
        from app.schemas.sla import ConversationSLATrackingUpdate
        from app.services.sla_service import ConversationSLATrackingService

        tracker = self._active_tracker(config, source_entity_id)
        if not tracker or bool(getattr(tracker, "is_resolved", False)):
            return
        # resolve implies responded — set both if not yet responded
        update_payload = {"is_resolved": True}
        if not bool(getattr(tracker, "is_responded", False)):
            update_payload["is_responded"] = True
        if actor_user_id:
            update_payload["resolved_by"] = actor_user_id
            if not bool(getattr(tracker, "is_responded", False)):
                update_payload["responded_by"] = actor_user_id
        svc = ConversationSLATrackingService(self.db)
        carry_contact_id = contact_id or (
            str(tracker.respond_contact_id)
            if tracker.respond_contact_id is not None
            else None
        )
        svc.update_tracking(
            str(tracker.id),
            ConversationSLATrackingUpdate(**update_payload),
        )

        if config.next_config_id:
            next_cfg = (
                self.db.query(FormSLAConfig)
                .filter(
                    FormSLAConfig.id == config.next_config_id,
                    FormSLAConfig.is_active.is_(True),
                )
                .first()
            )
            if next_cfg:
                self._start_for_config(
                    next_cfg, source_entity_id, contact_id=carry_contact_id
                )

    def _notify_assignee(
        self,
        tracker: ConversationSLATracking,
        *,
        kind: str = "assigned",
        reason: Optional[str] = None,
    ) -> None:
        if not tracker.assigned_to_id:
            return
        link = _form_detail_link(
            str(tracker.source_entity_type or ""),
            str(tracker.source_entity_id or ""),
        )
        type_label = (tracker.source_entity_type or "form").replace("_", " ")
        if kind == "assigned":
            title = f"New SLA assignment: {type_label}"
            body = (
                f"A {type_label} ({tracker.source_entity_id}) is assigned to you. "
                f"Respond by {tracker.due_at}." if tracker.due_at else
                f"A {type_label} ({tracker.source_entity_id}) is assigned to you."
            )
        elif kind == "escalated":
            title = f"SLA escalated to you: {type_label}"
            body = (
                f"A {type_label} ({tracker.source_entity_id}) has been escalated to you. "
                f"Reason: {reason or 'overdue'}. New deadline: {tracker.due_at}." if tracker.due_at else
                f"A {type_label} ({tracker.source_entity_id}) has been escalated to you."
            )
        else:
            title = f"SLA update: {type_label}"
            body = f"{type_label} {tracker.source_entity_id} status updated."

        try:
            NotificationService(self.db).create_with_channel_preferences(
                user_id=str(tracker.assigned_to_id),
                type="form_sla",
                title=title,
                body=body,
                data={
                    "tracking_id": str(tracker.id),
                    "source_entity_type": tracker.source_entity_type,
                    "source_entity_id": tracker.source_entity_id,
                    "link": link,
                },
                source_entity_type="form_sla_tracking",
                source_entity_id=str(tracker.id),
                event_type=kind,
                send_in_app=True,
                send_email=True,
                send_web_push=False,
            )
        except Exception as e:
            logger.warning(
                "Failed to send form SLA notification for tracker %s: %s",
                tracker.id,
                e,
            )

    def _write_event_log(
        self,
        *,
        tracker_id: str,
        event_type: str,
        from_tier: Optional[int] = None,
        to_tier: Optional[int] = None,
        reason: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        due_at: Optional[datetime] = None,
    ) -> None:
        from app.schemas.sla import ConversationSLAEventLogCreate
        from app.services.sla_service import ConversationSLATrackingService

        try:
            ConversationSLATrackingService(self.db).create_event_log(
                ConversationSLAEventLogCreate(
                    sla_tracking_id=tracker_id,
                    event_type=event_type,
                    from_tier=from_tier,
                    to_tier=to_tier,
                    event_at=_utc_naive_now(),
                    reason=reason,
                    assigned_to_id=assigned_to_id,
                    due_at=due_at,
                )
            )
        except Exception as e:
            logger.warning("Failed to write event log for tracker %s: %s", tracker_id, e)


def emit_form_event(
    db: Session,
    source_entity_type: str,
    source_entity_id: str,
    event_name: str,
    *,
    contact_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> None:
    """Module-level helper: thin wrapper for callers that don't hold an orchestrator."""
    FormSLAOrchestrator(db).emit_event(
        source_entity_type,
        source_entity_id,
        event_name,
        contact_id=contact_id,
        actor_user_id=actor_user_id,
    )
