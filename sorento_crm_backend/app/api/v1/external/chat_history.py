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
from app.schemas.external.chat_history import (
    ChatHistoryMessageIngestRequest,
    ChatHistoryMessageIngestResponse,
    ChatHistoryMessageItem,
    ChatHistoryMessagesRequest,
    ChatHistoryMessagesResponse,
)
from app.schemas.integration import IntegrationLogCreate
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
    """Ingest one chat message from n8n into local storage."""
    _ = current_user
    try:
        sent_at = _safe_utc_datetime_from_epoch_ms(payload.sent_at)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    insert_query = text(
        """
        INSERT INTO chat_histories (
            channel, contact_id, phone_number, message, sent_at, first_name, last_name, type,
            message_id, result, reply_to_message_id, reply_to_message, turn_id, ingest_at
        ) VALUES (
            :channel, :contact_id, :phone_number, :message, :sent_at, :first_name, :last_name, :type,
            :message_id, :result, :reply_to_message_id, :reply_to_message, :turn_id, :ingest_at
        )
        RETURNING id
        """
    )

    message_id: int | None = None
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
            },
        )
        message_id = result.scalar_one()
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
                request_payload=payload.model_dump_json(),
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

    return ChatHistoryMessageIngestResponse(id=message_id)


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
