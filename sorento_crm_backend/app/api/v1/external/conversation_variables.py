"""External API: per-contact conversation state stored on respond_contacts.session_vars.

Plain JSON store keyed by `respond_io_id` (Respond.io contact id, not internal UUID).
- GET  /{respond_io_id}  -> returns the stored session_vars dict
- PUT  /{respond_io_id}  -> body is an arbitrary JSON object, overwrites session_vars
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.conversation_variables import (
    ConversationStateOverwriteRequest,
    ConversationStateResponse,
)
from app.schemas.integration import IntegrationLogCreate
from app.services.conversation_variables_service import (
    get_for_contact,
    get_referenced_result_set,
    get_referenced_state,
    overwrite_for_contact,
)
from app.services.integration_service import IntegrationLogService


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{respond_io_id}",
    response_model=ConversationStateResponse,
    status_code=status.HTTP_200_OK,
)
def get_conversation_state(
    respond_io_id: str,
    message_id: str | None = Query(
        None,
        description="Respond.io message id; when set, two response-only keys are "
        "injected (DB untouched): `session_vars.referenced_result_set` (the `result` "
        "stored on that chat-history message) and `session_vars.referenced_state` "
        "(a 4-key projection of that turn's post-turn conversation state).",
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Return the raw `session_vars` JSON for the given respond.io contact id.

    With `?message_id=...`, also resolves the quoted message's stored result set and
    the quoted turn's post-turn state, returned under
    `session_vars.referenced_result_set` and `session_vars.referenced_state` - both
    always present (null on any miss) so n8n can branch deterministically. The two
    read different rows: the result set comes off the quoted row itself, the state off
    the INCOMING row of the same turn. The persisted `session_vars` is never modified
    by GET.
    """
    _ = current_user
    state = get_for_contact(db, respond_io_id=respond_io_id)
    if message_id is not None:
        state = {
            **state,
            "referenced_result_set": get_referenced_result_set(
                db, respond_io_id=respond_io_id, message_id=message_id
            ),
            "referenced_state": get_referenced_state(
                db, respond_io_id=respond_io_id, message_id=message_id
            ),
        }
    return ConversationStateResponse(respond_io_id=respond_io_id, session_vars=state)


@router.put(
    "/{respond_io_id}",
    response_model=ConversationStateResponse,
    status_code=status.HTTP_200_OK,
)
def overwrite_conversation_state(
    respond_io_id: str,
    payload: ConversationStateOverwriteRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Overwrite `session_vars` for the contact with the supplied JSON object."""
    _ = current_user

    response_status = status.HTTP_200_OK
    error_message: str | None = None
    response_payload: ConversationStateResponse | None = None
    _http_exc_to_reraise: HTTPException | None = None

    try:
        state = overwrite_for_contact(
            db, respond_io_id=respond_io_id, state=payload.root
        )
        response_payload = ConversationStateResponse(
            respond_io_id=respond_io_id, session_vars=state
        )
    except HTTPException as http_exc:
        response_status = http_exc.status_code
        error_message = str(http_exc.detail)
        _http_exc_to_reraise = http_exc
    except Exception as exc:
        logger.exception("conversation-state overwrite failed: %s", exc)
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = "Failed to overwrite conversation state."
        _http_exc_to_reraise = HTTPException(
            status_code=response_status, detail=error_message
        )

    try:
        request_headers = dict(request.headers)
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="respond_contacts.session_vars",
                business_id=str(uuid.uuid4()),
                external_reference=respond_io_id,
                direction="inbound",
                endpoint=str(request.url.path),
                http_method=request.method,
                request_headers=json.dumps(request_headers),
                request_payload=payload.model_dump_json(),
                status_code=response_status,
                status="success" if response_status < 400 else "failed",
                error_message=error_message,
            )
        )
    except Exception as log_error:
        logger.warning(
            "Failed to create integration log for conversation-state overwrite: %s",
            log_error,
            exc_info=True,
        )

    if _http_exc_to_reraise is not None:
        raise _http_exc_to_reraise

    assert response_payload is not None
    return response_payload
