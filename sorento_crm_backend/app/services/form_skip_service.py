"""Skip the next SLA stage - the generic engine (UAC-form-sla-skip-stage.md).

A stage config that declares `skip_event` may be closed by an explicit skip action
instead of its normal resolve. The stage resolves, `next_config_id` never spawns, and
the entity moves to `skip_terminal_status`.

The "don't advance" half needs no new engine code: `_resolve_for_active` only spawns
the next stage when the resolving event equals `advance_on_event`, so a skip event
that lives in `resolve_event` but NOT in `advance_on_event` resolves without
advancing. The next stage's own `start_event` will not match it either, which closes
the second spawn path for free.

Ordering matters and is contractual:

    resolve adapter -> permission -> active skippable stage -> source-status guard
      -> write terminal status -> COMMIT
      -> (best-effort, isolated) contact message, SLA emit, automation dispatch

Every guard runs before any write, so a 4xx never leaves a half-changed row. Every
side effect runs after the commit and can only warn - a notify failure must never 500
an action that already succeeded, because the caller's retry hits the source-status
guard and the missed side effect is never backfilled.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.sla import ConversationSLATracking, FormSLAConfig
from app.services.error_handler import AppException, handle_not_found, handle_validation_error
from app.services.form_sla_service import emit_form_event
from app.services.form_skip_registry import FormSkipAdapter, get_skip_adapter
from app.services.sla_scope import open_tracker_scope

logger = logging.getLogger(__name__)


class FormSkipService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Stage resolution
    # ------------------------------------------------------------------ #
    def _active_skippable_stage(
        self, source_entity_type: str, source_entity_id: str
    ) -> Tuple[Optional[ConversationSLATracking], Optional[FormSLAConfig]]:
        """The active (unresolved) stage row plus its config, if it declares a skip.

        A form-SLA stage is identified by (source_entity_type, team_set_code) - the
        tracker copies `team_set_code` from the config that spawned it, and that pair
        is unique per stage.

        Ordered by `initiated_at DESC` to match GET /form-sla-tracking exactly. Form SLA
        is multi-active by design (unlike conversation SLA, which allows one open row per
        contact), so an entity CAN carry several unresolved stage rows. The frontend
        offers the skip for the first unresolved row of that same ordering, so any other
        ordering here risks skipping a different stage from the one whose label the user
        just clicked.
        """
        tracker = (
            self.db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == source_entity_type,
                ConversationSLATracking.source_entity_id == str(source_entity_id),
                # A voided stage cannot be skipped - it is already gone.
                *open_tracker_scope(),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )
        if tracker is None:
            return None, None
        config = (
            self.db.query(FormSLAConfig)
            .filter(
                FormSLAConfig.source_entity_type == source_entity_type,
                FormSLAConfig.team_set_code == tracker.team_set_code,
                FormSLAConfig.is_active.is_(True),
            )
            .first()
        )
        if config is None or not (getattr(config, "skip_event", None) or "").strip():
            return tracker, None
        return tracker, config

    # ------------------------------------------------------------------ #
    # Guards
    # ------------------------------------------------------------------ #
    @staticmethod
    def _assert_permission(db: Session, adapter: FormSkipAdapter, actor_user_id: Optional[str]) -> None:
        """Per-entity permission, resolved by the adapter - never by config."""
        from app.services.user_service import UserPermissionService

        if not actor_user_id:
            raise AppException(status_code=403, message="Authentication required.")
        if not UserPermissionService(db).check_user_has_permission(
            actor_user_id, adapter.permission_slug
        ):
            raise AppException(
                status_code=403,
                message=f"Permission required: {adapter.permission_slug}",
            )

    def _load_entity(self, adapter: FormSkipAdapter, source_entity_id: str):
        entity = (
            self.db.query(adapter.model)
            .filter(adapter.model.id == str(source_entity_id))
            .first()
        )
        if entity is None:
            raise handle_not_found(adapter.display_name, str(source_entity_id))
        return entity

    @staticmethod
    def _assert_source_status(adapter: FormSkipAdapter, entity) -> str:
        current = (getattr(entity, adapter.status_attr, None) or "").strip().lower()
        allowed = adapter.allowed_source_statuses
        if allowed and current not in allowed:
            raise handle_validation_error(
                f"Cannot settle a {adapter.display_name} while status is {current!r}; "
                f"expected one of {allowed}."
            )
        return current

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def skip(
        self,
        source_entity_type: str,
        source_entity_id: str,
        *,
        actor_user_id: Optional[str] = None,
        note: Optional[str] = None,
        check_permission: bool = True,
    ) -> dict:
        adapter = get_skip_adapter(source_entity_type)
        if adapter is None:
            raise handle_validation_error(
                f"{source_entity_type!r} does not support this action."
            )

        if check_permission:
            self._assert_permission(self.db, adapter, actor_user_id)

        tracker, config = self._active_skippable_stage(source_entity_type, source_entity_id)
        if config is None:
            raise handle_validation_error(
                "This stage cannot be closed this way. There is no active, skippable "
                f"SLA stage for this {adapter.display_name}."
            )

        entity = self._load_entity(adapter, source_entity_id)
        self._assert_source_status(adapter, entity)

        skip_event = (config.skip_event or "").strip()
        terminal_status = (
            config.skip_terminal_status or ""
        ).strip() or skip_event

        # --- primary write, on its own --------------------------------- #
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        setattr(entity, adapter.status_attr, terminal_status)
        if adapter.resolved_at_attr and hasattr(entity, adapter.resolved_at_attr):
            setattr(entity, adapter.resolved_at_attr, now_utc)
        if adapter.resolved_by_attr and hasattr(entity, adapter.resolved_by_attr):
            setattr(entity, adapter.resolved_by_attr, actor_user_id)
        self.db.commit()
        self.db.refresh(entity)

        # --- everything after here is best-effort ---------------------- #
        self._run_side_effects(
            adapter,
            entity,
            note=note,
            skip_event=skip_event,
            actor_user_id=actor_user_id,
        )

        return {
            "status": terminal_status,
            "resolved_at": (
                getattr(entity, adapter.resolved_at_attr, None)
                if adapter.resolved_at_attr
                else None
            ),
            "message": (
                f"{adapter.display_name.capitalize()} marked as "
                f"{(config.skip_action_label or terminal_status).lower()}."
            ),
        }

    # ------------------------------------------------------------------ #
    # Post-commit side effects - each isolated, none may propagate
    # ------------------------------------------------------------------ #
    def _run_side_effects(
        self,
        adapter: FormSkipAdapter,
        entity,
        *,
        note: Optional[str],
        skip_event: str,
        actor_user_id: Optional[str],
    ) -> None:
        # 1. Resolve the SLA stage. The skip event is in resolve_event but not in
        #    advance_on_event, so this closes the stage WITHOUT spawning the next one.
        try:
            emit_form_event(
                self.db,
                adapter.source_entity_type,
                str(entity.id),
                skip_event,
                contact_id=getattr(entity, "contact_id", None),
                actor_user_id=actor_user_id,
            )
        except Exception as e:
            logger.warning(
                "Form SLA emit '%s' failed for %s %s: %s",
                skip_event,
                adapter.source_entity_type,
                entity.id,
                e,
            )

        self._notify_and_automate(adapter, entity, note=note, actor_user_id=actor_user_id)

    def _notify_and_automate(
        self,
        adapter: FormSkipAdapter,
        entity,
        *,
        note: Optional[str],
        actor_user_id: Optional[str],
    ) -> None:
        # 2. Tell the contact - exactly one message.
        if adapter.notify is not None:
            try:
                adapter.notify(self.db, entity, note, actor_user_id)
            except Exception:
                logger.exception(
                    "Skip notify failed for %s %s; status already committed.",
                    adapter.source_entity_type,
                    entity.id,
                )

        # 3. Admin-configured email automations. Fires nothing when none are set up.
        if adapter.automation_event and adapter.build_automation_context is not None:
            try:
                from app.services.automation_service import AutomationService

                context = adapter.build_automation_context(self.db, entity)
                AutomationService(self.db).dispatch_event(
                    adapter.automation_event,
                    context=context,
                    source_kind=adapter.source_entity_type,
                    source_id=str(entity.id),
                )
            except Exception:
                logger.exception(
                    "Automation dispatch_event(%s) failed for %s",
                    adapter.automation_event,
                    entity.id,
                )


def skip_form_stage(
    db: Session,
    source_entity_type: str,
    source_entity_id: str,
    *,
    actor_user_id: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Module-level convenience wrapper mirroring emit_form_event's shape."""
    return FormSkipService(db).skip(
        source_entity_type, source_entity_id, actor_user_id=actor_user_id, note=note
    )
