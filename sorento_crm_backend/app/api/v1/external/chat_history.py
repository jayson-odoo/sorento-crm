"""
External API: return latest n human messages from n8n_chat_histories for a contact (respond_io_id).

Auth: X-API-Key header (get_external_api_user).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import (
    ChatHistoryHumanMessagesRequest,
    ChatHistoryHumanMessagesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ChatHistoryHumanMessagesResponse, status_code=status.HTTP_200_OK)
def get_latest_human_messages(
    payload: ChatHistoryHumanMessagesRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Return the latest n human messages for a contact from n8n_chat_histories.

    Called by an external system (e.g. n8n) with contact_id (respond_io_id) and limit.
    Reads from n8n_chat_histories where session_id = contact_id and message type is "human",
    ordered by id descending, then returns the requested number of message content strings
    in chronological order (oldest first).

    **Auth:** X-API-Key header (external API key).

    **Body:**
    - contact_id (required): Respond.io contact id (maps to session_id in n8n_chat_histories).
    - limit (optional): Number of latest human messages to return (default 10, max 100).

    **Returns:** List of content strings only, e.g.:
    ```json
    {
      "content": [
        "Date today name shah delivery address my house...",
        "confirm, all good"
      ]
    }
    ```
    """
    contact_id = (payload.contact_id or "").strip()
    if not contact_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="contact_id is required.",
        )
    limit = max(1, min(100, payload.limit))

    query = text("""
        SELECT message
        FROM n8n_chat_histories
        WHERE session_id = :session_id
          AND message->>'type' = 'human'
        ORDER BY id DESC
        LIMIT :limit
    """)
    try:
        result = db.execute(query, {"session_id": contact_id, "limit": limit})
        rows = result.fetchall()
    except Exception as e:
        logger.exception("Failed to query n8n_chat_histories: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read chat history.",
        ) from e

    # message column is jsonb; rows are (message_dict,); reverse so oldest first
    raw_messages = [row[0] for row in rows]
    raw_messages.reverse()

    content_list: list[str] = []
    for raw in raw_messages:
        if not raw or not isinstance(raw, dict):
            continue
        content = raw.get("content")
        if isinstance(content, str):
            content_list.append(content)
        elif content is not None:
            content_list.append(str(content))

    return ChatHistoryHumanMessagesResponse(content=content_list)
