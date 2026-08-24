"""Form-SLA deferred actions - read, in-grace cancel, post-grace undo.

The domain routes keep their own URLs; deferral happens inside them. These three exist
only for what the domain routes cannot express: what is currently pending on a form, and
the two ways to take an action back.

Permission split is deliberate:
 - cancel (in-grace) has NO permission slug. Nothing has happened yet and the action
    belongs to whoever started it, so requiring a grant to undo your own two-second-old
    click would be theatre.
 - undo (post-grace) requires `sla_management.form_sla.undo_action`, because by then it
    is a compensating reversal that voids someone else's task.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.services.error_handler import handle_internal_error, handle_validation_error
from app.services.form_action_registry import get_action
from app.services.form_action_service import FormActionService
from app.services.form_sla_service import FORM_SLA_TYPES

# Module scope, not per-endpoint: the lazy commit in GET /current calls
# `action_for(row.action_key)` and on an API worker that has never served a
# dispatching request the registry would be empty - the poll for a due action would
# 500 with a KeyError, react-query would stop polling, and the banner would vanish
# while the action stayed parked server-side (the exact loss AC-D-5 forbids).
import app.services.form_actions  # noqa: E402,F401  (registers the actions)

router = APIRouter()


class _UndoRequest(BaseModel):
    source_entity_type: str
    source_entity_id: str
    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Why the action is being reversed. Mandatory - an undo without one "
        "is unexplainable a month later.",
    )


def _assert_known_type(source_entity_type: str) -> None:
    if source_entity_type not in FORM_SLA_TYPES:
        raise handle_validation_error(
            f"Unsupported form type: {source_entity_type!r}."
        )


def _is_admin(db: Session, user_id: Optional[str]) -> bool:
    from app.services.user_service import UserPermissionService

    if not user_id:
        return False
    return bool(
        UserPermissionService(db).get_user_role_slugs(str(user_id))
        & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}
    )


def _serialize_pending(db: Session, row, viewer_id: Optional[str]) -> dict:
    from app.models.user import User

    action = get_action(row.action_key)
    requester = (
        db.query(User).filter(User.id == row.requested_by_id).first()
        if row.requested_by_id
        else None
    )
    window = None
    if row.commit_at and row.created_at:
        # Derived from the two stored UTC stamps so the bar keeps a fixed denominator
        # across a remount - the client must never measure the window itself.
        window = max(1, int((row.commit_at - row.created_at).total_seconds()))
    is_requester = viewer_id is not None and str(row.requested_by_id or "") == str(viewer_id)
    return {
        "id": str(row.id),
        "action_key": row.action_key,
        "action_label": action.label if action else "Action",
        "requested_by_id": str(row.requested_by_id) if row.requested_by_id else None,
        "requested_by_name": (
            ((requester.name or requester.email) if requester else None) or "a teammate"
        ),
        "commit_at": row.commit_at.isoformat() if row.commit_at else None,
        "window_seconds": window,
        "can_cancel": is_requester or _is_admin(db, viewer_id),
    }


@router.get("/current")
async def get_current_form_action(
    source_entity_type: str = Query(...),
    source_entity_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The pending action on a form, or null.

    Also performs the lazy commit: a pending row whose `commit_at` has passed is
    executed here before the response is built, so a stopped scheduler delays an action
    but never loses one (AC-D-5).
    """
    _assert_known_type(source_entity_type)
    service = FormActionService(db)
    try:
        row = service.pending_for(source_entity_type, source_entity_id)
        if row is not None and row.commit_at is not None:
            from datetime import datetime

            if row.commit_at <= datetime.utcnow():
                service.commit_one(row)
                row = service.pending_for(source_entity_type, source_entity_id)

        # The terminal outcome of the most recent action that did NOT apply. The FE
        # shows it only when it matches the pending action it was just watching, so
        # an old failure cannot resurface on an unrelated page load.
        terminal = service.last_terminal_outcome(source_entity_type, source_entity_id)
        last_outcome = None
        if terminal is not None:
            terminal_action = get_action(terminal.action_key)
            last_outcome = {
                "action_id": str(terminal.id),
                "action_key": terminal.action_key,
                "action_label": terminal_action.label if terminal_action else "Action",
                "status": terminal.status,
                "reason": (terminal.error_text or "").strip()
                or "the form changed while the action was waiting",
                "resolved_at": (
                    terminal.resolved_at.isoformat() if terminal.resolved_at else None
                ),
            }

        return {
            "pending": _serialize_pending(db, row, current_user.get("id")) if row else None,
            "last_outcome": last_outcome,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{action_id}/cancel")
async def cancel_form_action(
    action_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """In-grace undo. No permission slug by design - see the module docstring."""
    try:
        service = FormActionService(db)
        uid = current_user.get("id")
        row = service.cancel(
            action_id, actor_id=uid, actor_is_admin=_is_admin(db, uid)
        )
        return {"status": row.status, "message": "Action withdrawn. Nothing was sent."}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/undo")
async def undo_form_action(
    body: _UndoRequest,
    current_user: dict = Depends(
        require_permission("sla_management.form_sla.undo_action")
    ),
    db: Session = Depends(get_db),
):
    """Post-grace undo. Reverses the last committed action on the form.

    Wired to the guardrail and the inverse in S4; until then it refuses rather than
    half-reversing, so an eligible-looking button can never produce a partial rollback.
    """
    _assert_known_type(body.source_entity_type)
    if not body.reason.strip():
        raise handle_validation_error("A reason is required to undo an action.")

    try:
        import app.services.form_actions  # noqa: F401  (registers the actions)

        row = FormActionService(db).undo(
            source_entity_type=body.source_entity_type,
            source_entity_id=body.source_entity_id,
            actor_id=current_user.get("id"),
            reason=body.reason,
            # The route dependency already enforced the slug; passing it through keeps
            # the guardrail's refusal reasons in one place rather than split across
            # a dependency and a service check.
            has_permission=True,
        )
        return {
            "status": row.status,
            "action_key": row.action_key,
            "message": "Action reversed. Everyone involved has been notified.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/eligibility")
async def get_undo_eligibility(
    source_entity_type: str = Query(...),
    source_entity_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Whether the last committed action on this form can be reversed, and if not, why.

    The FE never guesses (AC-PG-6). The same guardrail runs again at execute time, so a
    stale page that still renders an enabled button is refused server-side (AC-PG-7).
    """
    _assert_known_type(source_entity_type)
    try:
        import app.services.form_actions  # noqa: F401  (registers the actions)

        from app.services.form_action_undo import evaluate
        from app.services.user_service import UserPermissionService

        has_permission = UserPermissionService(db).check_user_has_permission(
            str(current_user["id"]), "sla_management.form_sla.undo_action"
        )
        return evaluate(
            db,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            has_permission=has_permission,
        ).to_payload()
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
