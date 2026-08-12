"""One dispatch-or-defer entry point for every domain router (PLAN-form-sla-undo.md).

The PR/SF router grew the first copy of this glue; the stock-inquiry, complaint and
ticket routers need the identical decision (browser + grace window => park and 202,
anything else => run now). Four hand-rolled copies would drift - the channel sniff and
the 202 body have to stay byte-identical or the shared FE hook misreads one form type.

Routers call `dispatch_or_defer(...)`; a `JSONResponse` return means "deferred, hand
this straight back", anything else is the wrapped service method's own result.
"""

from __future__ import annotations

from typing import Optional, Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session


def dispatch_or_defer(
    db: Session,
    current_user: dict,
    request: Optional[Request],
    *,
    action_key: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
    event_name: str,
) -> Union[JSONResponse, object]:
    """Route one form action through the deferral dispatcher.

    With no grace configured (the shipped default) this runs the wrapped service method
    exactly as before and returns its result. With a grace window AND a browser session,
    it parks the action and returns the 202 body the FE countdown consumes.
    """
    from app.models.sla import FORM_ACTION_CHANNEL_IMMEDIATE, FORM_ACTION_CHANNEL_UI
    from app.services.form_action_grace import grace_seconds_for
    from app.services.form_action_service import FormActionService
    import app.services.form_actions  # noqa: F401  (registers the actions)

    # Read the channel off the REQUEST, not the user dict: `auth_method` is only set by
    # the api-key-capable dependency, so endpoints guarded by plain `require_permission`
    # never carry it and would silently never defer. An X-API-Key header is the exact
    # signal - a machine caller has no browser to show a countdown in.
    channel = (
        FORM_ACTION_CHANNEL_IMMEDIATE
        if (request is not None and request.headers.get("x-api-key")) or request is None
        else FORM_ACTION_CHANNEL_UI
    )
    outcome = FormActionService(db).dispatch(
        action_key=action_key,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        actor_id=(current_user or {}).get("id"),
        channel=channel,
        grace_seconds=grace_seconds_for(db, entity_type, event_name=event_name),
    )
    if outcome.deferred:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "deferred": True,
                "pending_action_id": outcome.action_id,
                "action_key": action_key,
                "commit_at": outcome.commit_at.isoformat() if outcome.commit_at else None,
                "window_seconds": outcome.window_seconds,
            },
        )
    return outcome.result
