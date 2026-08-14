"""External API for channel-based chat history ingestion and retrieval."""
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.chat_history import CHAT_HISTORY_DEDUPE_PREDICATE
from app.schemas.external.chat_history import (
    ChatHistoryMessageIngestRequest,
    ChatHistoryMessageIngestResponse,
    ChatHistoryMessageItem,
    ChatHistoryMessagesRequest,
    ChatHistoryMessagesResponse,
)
from app.schemas.integration import IntegrationLogCreate
from app.services.chat_message_resolver import respond_ts_from_message_id
from app.services.integration_service import IntegrationLogService

logger = logging.getLogger(__name__)

router = APIRouter()


def _coerce_result_list(raw) -> list | None:
    """Coerce a stored jsonb `result` value into a list (None when absent/malformed)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    return raw if isinstance(raw, list) else None


def _safe_utc_datetime_from_epoch_ms(epoch_ms: int) -> datetime:
    if epoch_ms <= 0:
        raise ValueError("sent_at must be a valid epoch milliseconds value.")
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


@router.post("/messages", response_model=ChatHistoryMessageIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_chat_message(
    payload: ChatHistoryMessageIngestRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Ingest one chat message from n8n into local storage.

    Idempotent on the Respond ``message_id`` for a given contact (AC-J5): a
    message mirrored twice resolves to the one row and answers with the same id
    and ``status: "duplicate"``. A payload with no ``message_id`` has nothing to
    dedupe on and always inserts, as it always did.
    """
    _ = current_user
    try:
        sent_at = _safe_utc_datetime_from_epoch_ms(payload.sent_at)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # AC-J5: a CRM drawer send reaches this endpoint TWICE - once from the direct
    # respond-send-user webhook lane, once from Respond's own outgoing-message
    # trigger - so the same WhatsApp message must resolve to one row whichever
    # lane wins the race. The conflict target is the partial unique index from
    # migration 326; its predicate is repeated verbatim because Postgres infers
    # the arbiter index from it (see CHAT_HISTORY_DEDUPE_PREDICATE). Rows with no
    # message_id are outside the index and keep inserting exactly as before.
    #
    # DO UPDATE, not DO NOTHING: DO NOTHING returns no row (so the caller could
    # not be told which row its message is), and the losing lane often carries
    # context the winner lacked (turn_id, the quoted message). Fill-if-null only:
    # a mirror re-states a message, it never edits it.
    insert_query = text(
        f"""
        INSERT INTO chat_histories (
            channel, contact_id, phone_number, message, sent_at, first_name, last_name, type,
            message_id, result, reply_to_message_id, reply_to_message, turn_id, ingest_at,
            respond_ts, state_trace
        ) VALUES (
            :channel, :contact_id, :phone_number, :message, :sent_at, :first_name, :last_name, :type,
            :message_id, :result, :reply_to_message_id, :reply_to_message, :turn_id, :ingest_at,
            :respond_ts, :state_trace
        )
        ON CONFLICT (contact_id, message_id) WHERE {CHAT_HISTORY_DEDUPE_PREDICATE}
        DO UPDATE SET
            first_name = COALESCE(chat_histories.first_name, EXCLUDED.first_name),
            last_name = COALESCE(chat_histories.last_name, EXCLUDED.last_name),
            result = COALESCE(chat_histories.result, EXCLUDED.result),
            reply_to_message_id = COALESCE(
                chat_histories.reply_to_message_id, EXCLUDED.reply_to_message_id
            ),
            reply_to_message = COALESCE(
                chat_histories.reply_to_message, EXCLUDED.reply_to_message
            ),
            turn_id = COALESCE(chat_histories.turn_id, EXCLUDED.turn_id),
            respond_ts = COALESCE(chat_histories.respond_ts, EXCLUDED.respond_ts),
            state_trace = COALESCE(chat_histories.state_trace, EXCLUDED.state_trace)
        RETURNING id, (xmax <> 0) AS already_existed
        """
    )

    message_id: int | None = None
    already_existed = False
    status_code = status.HTTP_201_CREATED
    error_message: str | None = None

    try:
        result = db.execute(
            insert_query,
            {
                "channel": payload.channel,
                "contact_id": payload.contact_id,
                "phone_number": payload.phone_number,
                "message": payload.message,
                "sent_at": sent_at,
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "type": payload.type,
                "message_id": payload.message_id,
                "result": json.dumps(payload.result) if payload.result is not None else None,
                "reply_to_message_id": payload.reply_to_message_id,
                "reply_to_message": payload.reply_to_message,
                "turn_id": payload.turn_id,
                # Our clock at ingest. Never the SLA clock — its only job is to make
                # webhook lag (ingest_at - respond_ts) separable from agent time.
                "ingest_at": datetime.now(tz=timezone.utc).replace(tzinfo=None),
                # Respond's `messageId` IS the message's epoch-microsecond timestamp,
                # so the SLA clock is already in this payload — no resolver round trip
                # needed for it. Null when the id isn't a plausible timestamp; the
                # resolver still backstops those rows.
                "respond_ts": respond_ts_from_message_id(
                    payload.message_id, sent_at=sent_at
                ),
                # `is not None`, NOT truthiness: a `{}` trace (or `{"after": null}`)
                # must round-trip, so the guard must not be what drops it. json.dumps
                # of {"after": None} emits "after": null — the signal the view keys on.
                "state_trace": json.dumps(payload.state_trace)
                if payload.state_trace is not None
                else None,
            },
        )
        row = result.one()
        message_id = row.id
        already_existed = bool(row.already_existed)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to insert chat history: %s", e)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = "Failed to ingest chat history message."

    try:
        request_headers = dict(request.headers)
        # Avoid persisting sensitive API key values in integration logs.
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"

        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="chat_histories",
                business_id=str(uuid.uuid4()),
                external_reference=str(payload.contact_id),
                direction="inbound",
                endpoint=str(request.url.path),
                http_method=request.method,
                request_headers=json.dumps(request_headers),
                # Exclude state_trace: it is already persisted as jsonb on the row.
                # integration_logs has no purge, so logging it here would store the
                # whole trace a second time, as text, write-only, forever.
                request_payload=payload.model_dump_json(exclude={"state_trace"}),
                status_code=status_code,
                status="success" if status_code < 400 else "failed",
                error_message=error_message,
            )
        )
    except Exception as log_error:
        logger.warning("Failed to create integration log for chat history ingestion: %s", log_error, exc_info=True)

    if message_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest chat history message.",
        )

    # 201 either way: the caller (n8n) treats anything else as a lane failure and
    # retries, which is exactly the loop this endpoint exists to end. "duplicate"
    # names the outcome in the body instead, mirroring the conversation-SLA
    # create's `already_active` marker.
    return ChatHistoryMessageIngestResponse(
        id=message_id, status="duplicate" if already_existed else "created"
    )


@router.post("", response_model=ChatHistoryMessagesResponse, status_code=status.HTTP_200_OK)
def get_chat_history_messages(
    payload: ChatHistoryMessagesRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Return chat history from local high-volume channel-based chat storage."""
    _ = current_user
    limit = max(1, min(500, payload.limit))
    order = payload.order.lower()
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order must be 'asc' or 'desc'.")

    # Fetch latest rows first using descending index order, then optionally reverse for ascending response.
    query = text(
        """
        SELECT id, channel, contact_id, phone_number, message, sent_at, first_name, last_name, type,
               message_id, result, reply_to_message_id, reply_to_message
        FROM chat_histories
        WHERE channel = :channel
          AND contact_id = :contact_id
        ORDER BY sent_at DESC, id DESC
        LIMIT :limit
        """
    )
    try:
        result = db.execute(
            query,
            {"channel": payload.channel, "contact_id": payload.contact_id, "limit": limit},
        )
        rows = result.fetchall()
    except Exception as e:
        logger.exception("Failed to query chat_histories: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read chat history.",
        ) from e

    messages = [
        ChatHistoryMessageItem(
            id=row.id,
            channel=row.channel,
            contact_id=row.contact_id,
            phone_number=row.phone_number,
            message=row.message,
            sent_at=row.sent_at,
            first_name=row.first_name,
            last_name=row.last_name,
            type=row.type,
            message_id=row.message_id,
            result=_coerce_result_list(row.result),
            reply_to_message_id=row.reply_to_message_id,
            reply_to_message=row.reply_to_message,
        )
        for row in rows
    ]
    if order == "asc":
        messages.reverse()

    return ChatHistoryMessagesResponse(messages=messages)
