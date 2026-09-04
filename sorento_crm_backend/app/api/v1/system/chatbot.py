"""System API: the turn trace behind System > Chat History (S2b, AC-255/AC-257).

Three read-or-act routes over `chatbot.turns`, for the operator journey "a customer says
the bot answered wrongly, what did it actually do?":

* `GET /turns` - one contact's turns, newest first, cursor-paged;
* `GET /turns/failed-contacts` - which contacts have a failed turn in a range, so the
  list can filter to them without pulling every turn;
* `POST /turns/{id}/retry` - re-post the original message at the ingress (R4: the only
  retry there is, and only a person can ask for it).

Two slugs, deliberately. `system.chat_history.view` reads the trace - the same grant that
already reads the transcript it hangs under. `system.chat_history.manage` re-injects a
WhatsApp turn at a real customer, which is a different thing to hand out.

This module is an authorised importer of `app.services.chatbot` (AC-002): the retry seam
lives in the module package, and the trace screen is the module's own read surface.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.chatbot_turn import ChatbotTurn
from app.schemas.chatbot_turn import (
    ChatbotTurnListResponse,
    FailedContactListResponse,
    RetryTurnResponse,
)
from app.services.chatbot.contracts import TURN_STAGES
from app.services.chatbot.dispatch import (
    ReinjectFailed,
    RetryUnavailable,
    reinject_envelope,
    retry_available,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chatbot")

VIEW = "system.chat_history.view"
MANAGE = "system.chat_history.manage"

# The engine's own vocabulary. An unknown value is a 422 rather than an empty page,
# because "no turns are `delivered`" and "there is no such status as `delivered`" are
# different answers and only one of them means the caller has a bug.
TURN_STATUSES = ("queued", "processing", "delegated", "done", "failed")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _encode_cursor(row: ChatbotTurn) -> str:
    """Opaque keyset cursor: the last row's sort key, not an offset.

    Offsets shift under a table that is being written to while an operator pages, which on
    a newest-first list means rows appearing twice or not at all. `id` breaks ties so two
    turns created in the same millisecond still have a total order.
    """
    payload = {"created_at": row.created_at.isoformat(), "id": str(row.id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["created_at"]), payload["id"]
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid cursor. Use the `next_cursor` from the previous page.",
        ) from exc


@router.get("/turns", response_model=ChatbotTurnListResponse)
def list_turns(
    contact_respond_id: str | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    turn_status: str | None = Query(None, alias="status"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """One contact's turns with their full trace, newest first."""
    _ = current_user

    if turn_status is not None and turn_status not in TURN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown status {turn_status!r}. Expected one of: {', '.join(TURN_STATUSES)}.",
        )

    query = db.query(ChatbotTurn)
    if contact_respond_id:
        query = query.filter(ChatbotTurn.contact_respond_id == contact_respond_id)
    if from_ is not None:
        query = query.filter(ChatbotTurn.created_at >= from_)
    if to is not None:
        query = query.filter(ChatbotTurn.created_at <= to)
    if turn_status is not None:
        query = query.filter(ChatbotTurn.status == turn_status)
    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        # Strictly AFTER the last row in newest-first order: older, or same instant with
        # a smaller id.
        query = query.filter(
            (ChatbotTurn.created_at < cursor_created_at)
            | ((ChatbotTurn.created_at == cursor_created_at) & (ChatbotTurn.id < cursor_id))
        )

    # One extra row answers "is there another page?" without a second COUNT over a table
    # that only grows.
    rows = (
        query.order_by(desc(ChatbotTurn.created_at), desc(ChatbotTurn.id))
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return ChatbotTurnListResponse(
        items=page,
        next_cursor=_encode_cursor(page[-1]) if has_more and page else None,
    )


@router.get("/turns/failed-contacts", response_model=FailedContactListResponse)
def failed_contacts(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Contacts with at least one failed turn in the range (AC-255).

    What the list's "Failed turns only" filter needs is which contacts to show and what
    went wrong last - two aggregates - not the turns themselves. Answering it by paging
    `/turns` and grouping in the browser would move thousands of rows to answer a question
    about tens, and would be wrong the moment the answer spans a page boundary.
    """
    _ = current_user

    query = db.query(ChatbotTurn).filter(ChatbotTurn.status == "failed")
    if from_ is not None:
        query = query.filter(ChatbotTurn.created_at >= from_)
    if to is not None:
        query = query.filter(ChatbotTurn.created_at <= to)

    aggregates = (
        query.with_entities(
            ChatbotTurn.contact_respond_id.label("contact_respond_id"),
            func.count(ChatbotTurn.id).label("count"),
            func.max(ChatbotTurn.created_at).label("last_failed_at"),
        )
        .group_by(ChatbotTurn.contact_respond_id)
        .order_by(desc(func.max(ChatbotTurn.created_at)))
        .all()
    )
    if not aggregates:
        return FailedContactListResponse(items=[])

    # The stage of the LAST failure per contact. A second small query rather than a window
    # function so the aggregate above stays legible and portable; the input is already
    # narrowed to contacts that have a failure.
    latest_stage: dict[str, str | None] = {}
    contact_ids = [row.contact_respond_id for row in aggregates]
    stage_rows = (
        query.with_entities(
            ChatbotTurn.contact_respond_id,
            ChatbotTurn.stage,
            ChatbotTurn.created_at,
        )
        .filter(ChatbotTurn.contact_respond_id.in_(contact_ids))
        .order_by(ChatbotTurn.contact_respond_id, desc(ChatbotTurn.created_at))
        .all()
    )
    for contact_id, stage, _created in stage_rows:
        latest_stage.setdefault(contact_id, stage)

    return FailedContactListResponse(
        items=[
            {
                "contact_respond_id": row.contact_respond_id,
                "last_failed_stage": latest_stage.get(row.contact_respond_id),
                "last_failed_at": row.last_failed_at,
                "count": row.count,
            }
            for row in aggregates
        ]
    )


@router.post("/turns/{turn_id}/retry", response_model=RetryTurnResponse)
def retry_turn(
    turn_id: str,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    """Re-post this turn's ORIGINAL message at the ingress (AC-705, R4).

    The row is NOT re-run here and NOT edited: it stays `failed`, keeps its trace, and
    gains a marker. The retry arrives back the ordinary way, as its own row with the next
    attempt - which is what makes the retried turn get the same ordering, the same lanes
    and the same sending path a live message gets.
    """
    _ = current_user

    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn not found.")

    if row.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only a failed turn can be retried; this one is {row.status}. "
                "Nothing retries automatically (R4)."
            ),
        )
    if row.retry_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A retry for this turn is already on its way. Wait for it to arrive as a "
                "new turn before asking again."
            ),
        )

    try:
        reinject_envelope(row)
    except RetryUnavailable as exc:
        # Not an error the operator caused, and not a 500: this environment simply has no
        # ingress wired, which is the correct state for a developer machine.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "retry_unavailable", "message": str(exc)},
        ) from exc
    except ReinjectFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The message could not be re-injected: {exc}",
        ) from exc

    now = datetime.now(timezone.utc)
    row.retry_requested_at = now
    # The trace is the operator's record of this turn, and asking for a retry is something
    # that happened to it. Appended in the same shape every stage record has, so the
    # timeline renders it without a special case.
    trace = list(row.trace or [])
    trace.append(
        {
            # The stage this turn stopped at, so the note sits with the failure it belongs
            # to rather than inventing a ninth stage the timeline would not know how to
            # label. `intake` / `queued` / `casual_llm` are row-only stages, hence the
            # fallback.
            "stage": row.stage if row.stage in TURN_STAGES else "sent",
            "status": "ok",
            "started_at": now.isoformat(),
            "ms": 0,
            "summary": "Retry requested by an operator.",
            "why": (
                "The original message was re-posted to the chatbot ingress; it will arrive "
                "as a new turn with the next attempt number."
            ),
            "facts": {"attempt": row.attempt + 1, "requested_at": now.isoformat()},
            "error": None,
            "raw": {"retry": True, "from_attempt": row.attempt},
        }
    )
    row.trace = trace
    db.commit()

    return RetryTurnResponse(turn_id=str(row.id), attempt=row.attempt + 1)


@router.get("/retry-availability")
def retry_availability(
    current_user: dict = Depends(require_permission(VIEW)),
):
    """Whether Retry can work here at all, so the UI disables rather than offers a 409.

    A button that always 409s teaches an operator to distrust the screen; one that is
    visibly unavailable, with the reason, teaches them it is an environment thing.
    """
    _ = current_user
    return {
        "available": retry_available(),
        "reason": None
        if retry_available()
        else "Retry is not configured in this environment.",
    }
