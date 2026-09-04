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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_permission
from app.models.chatbot_turn import ChatbotTurn
from app.schemas.integration import IntegrationLogCreate
from app.schemas.chatbot_turn import (
    ChatbotTurnListResponse,
    FailedContactListResponse,
    RetryTurnResponse,
)
from app.services.chatbot.contracts import TURN_STAGES
from app.services.integration_service import IntegrationLogService
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
# The list filter shows a roster of contacts to open, not a report. Past a couple of
# hundred the answer is "something is broadly wrong", which is a different screen.
FAILED_CONTACTS_LIMIT = 200
FAILED_CONTACTS_DEFAULT_DAYS = 7


def _retry_in_flight(row: ChatbotTurn) -> bool:
    """Is a requested retry still expected to arrive?

    The marker is cleared by the re-injected turn arriving. If it never does - n8n dropped
    it, the contact was deleted, the workflow was mid-deploy - the row would be
    un-retryable forever, which turns one lost message into a permanently stuck one. After
    `chatbot_retry_stale_minutes` the operator may try again.
    """
    if row.retry_requested_at is None:
        return False
    requested_at = row.retry_requested_at
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    window = timedelta(minutes=max(1, int(settings.chatbot_retry_stale_minutes)))
    return datetime.now(timezone.utc) - requested_at < window


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
    available = retry_available()
    return ChatbotTurnListResponse(
        items=page,
        next_cursor=_encode_cursor(page[-1]) if has_more and page else None,
        retry_available=available,
        retry_unavailable_reason=None
        if available
        else "Retry is not configured in this environment.",
    )


@router.get("/turns/failed-contacts", response_model=FailedContactListResponse)
def failed_contacts(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    limit: int = Query(FAILED_CONTACTS_LIMIT, ge=1, le=FAILED_CONTACTS_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Contacts with at least one failed turn in the range (AC-255).

    What the list's "Failed turns only" filter needs is which contacts to show and what
    went wrong last - two aggregates - not the turns themselves. Answering it by paging
    `/turns` and grouping in the browser would move thousands of rows to answer a question
    about tens, and would be wrong the moment the answer spans a page boundary.

    A range is REQUIRED (a default of the last 7 days when neither bound is given): this
    is the one query here that does not start from a contact id, so unbounded it is a scan
    of every failed turn ever recorded, growing forever, behind a toggle.
    """
    _ = current_user

    if from_ is None and to is None:
        from_ = datetime.now(timezone.utc) - timedelta(days=FAILED_CONTACTS_DEFAULT_DAYS)

    window = [ChatbotTurn.status == "failed"]
    if from_ is not None:
        window.append(ChatbotTurn.created_at >= from_)
    if to is not None:
        window.append(ChatbotTurn.created_at <= to)

    # The counts.
    aggregates = (
        db.query(
            ChatbotTurn.contact_respond_id.label("contact_respond_id"),
            func.count(ChatbotTurn.id).label("count"),
            func.max(ChatbotTurn.created_at).label("last_failed_at"),
        )
        .filter(*window)
        .group_by(ChatbotTurn.contact_respond_id)
        .order_by(desc(func.max(ChatbotTurn.created_at)))
        .limit(limit)
        .all()
    )
    if not aggregates:
        return FailedContactListResponse(items=[])

    contact_ids = [row.contact_respond_id for row in aggregates]
    # The stage of the LAST failure per contact. DISTINCT ON returns ONE row per contact
    # rather than every failed row for the app to fold - on a contact with hundreds of
    # failures the difference is the whole result set.
    latest = (
        db.query(ChatbotTurn.contact_respond_id, ChatbotTurn.stage)
        .filter(*window, ChatbotTurn.contact_respond_id.in_(contact_ids))
        .distinct(ChatbotTurn.contact_respond_id)
        .order_by(ChatbotTurn.contact_respond_id, desc(ChatbotTurn.created_at))
        .all()
    )
    latest_stage = {contact_id: stage for contact_id, stage in latest}

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
    request: Request,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    """Re-post this turn's ORIGINAL message at the ingress (AC-705, R4).

    The row is NOT re-run here and NOT edited: it stays `failed`, keeps its trace, and
    gains a marker. The retry arrives back the ordinary way, as its own row with the next
    attempt - which is what makes the retried turn get the same ordering, the same lanes
    and the same sending path a live message gets.

    **The marker is written and COMMITTED before the POST**, and rolled back if the POST
    does not happen. The other order looks tidier and is a race: n8n can deliver the
    re-injected message, and the engine can look for the marker, before this request has
    committed it - so the engine would read `failed` with no marker, call it a duplicate,
    and the retry would vanish while the marker stayed set forever.
    """
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
    if _retry_in_flight(row):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A retry for this turn is already on its way. Wait for it to arrive as a "
                "new turn before asking again."
            ),
        )

    now = datetime.now(timezone.utc)
    actor_id = str(current_user.get("id") or "")

    # Claim FIRST, then send. See the docstring.
    row.retry_requested_at = now
    trace = list(row.trace or [])
    trace.append(
        {
            "kind": "note",  # not a stage: rendered as a footer line, not a timeline row
            "stage": row.stage if row.stage in TURN_STAGES else "sent",
            "status": "ok",
            "started_at": now.isoformat(),
            "ms": 0,
            "summary": "Retry requested by an operator.",
            "why": (
                "The original message was re-posted to the chatbot ingress; it will arrive "
                "as a new turn with the next attempt number."
            ),
            "facts": {
                "attempt": row.attempt + 1,
                "requested_at": now.isoformat(),
                "requested_by": actor_id,
            },
            "error": None,
            "raw": {"retry": True, "from_attempt": row.attempt, "requested_by": actor_id},
        }
    )
    row.trace = trace
    db.commit()

    outcome_status = 200
    error_message: str | None = None
    try:
        reinject_envelope(row)
    except (RetryUnavailable, ReinjectFailed) as exc:
        # Nothing was accepted by the ingress, so the claim must not stand: another
        # operator has to be able to try again, and a marker nobody will ever clear would
        # make this row permanently un-retryable.
        row.retry_requested_at = None
        row.trace = trace[:-1]
        db.commit()
        unavailable = isinstance(exc, RetryUnavailable)
        outcome_status = 409 if unavailable else 502
        error_message = str(exc)
        _log_retry(db, request, row, actor_id, outcome_status, error_message)
        if unavailable:
            # Not an error the operator caused, and not a 500: this environment simply has
            # no ingress wired, which is the correct state for a developer machine.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "retry_unavailable", "message": error_message},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The message could not be re-injected: {error_message}",
        ) from exc

    _log_retry(db, request, row, actor_id, outcome_status, error_message)
    return RetryTurnResponse(turn_id=str(row.id), attempt=row.attempt + 1)


def _log_retry(
    db: Session,
    request: Request,
    row: ChatbotTurn,
    actor_id: str,
    status_code: int,
    error_message: str | None,
) -> None:
    """An `integration_log` row for the outbound POST, success AND failure.

    Same rule every Respond.io send follows: an outbound call that touched a customer
    leaves a record whichever way it went, so "did we re-send that?" is answerable from
    the database rather than from someone's memory of a button click.
    """
    try:
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="chatbot.turns",
                business_id=str(row.id),
                external_reference=row.contact_respond_id,
                direction="outbound",
                endpoint=str(request.url.path),
                http_method="POST",
                request_payload=json.dumps(
                    {
                        "turn_id": str(row.id),
                        "message_id": row.message_id,
                        "from_attempt": row.attempt,
                        "requested_by": actor_id,
                    }
                ),
                status_code=status_code,
                status="success" if status_code < 400 else "failed",
                error_message=error_message,
            )
        )
    except Exception as exc:  # noqa: BLE001 - the log must never fail the retry
        logger.warning("chatbot retry: integration log failed: %s", exc, exc_info=True)
