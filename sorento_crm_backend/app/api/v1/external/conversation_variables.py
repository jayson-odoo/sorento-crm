"""External API: per-conversation variables collected by n8n turn-by-turn."""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.conversation_variables import (
    ConversationVariablesUpsertRequest,
    ConversationVariablesUpsertResponse,
)
from app.schemas.integration import IntegrationLogCreate
from app.services.conversation_variables_service import upsert_for_contact
from app.services.integration_service import IntegrationLogService


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/upsert",
    response_model=ConversationVariablesUpsertResponse,
    status_code=status.HTTP_200_OK,
)
def upsert_conversation_variables(
    payload: ConversationVariablesUpsertRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Append the latest turn's variables, slide the window, return the merged set.

    Sends the merged dict for `inquiry_type` back to n8n so the next turn can
    reference any slot already collected in this conversation.
    """
    _ = current_user

    response_status = status.HTTP_200_OK
    error_message: str | None = None
    response_payload: ConversationVariablesUpsertResponse | None = None

    try:
        state = upsert_for_contact(
            db,
            respond_io_id=payload.contact_id,
            inquiry_type=payload.inquiry_type,
            variables=payload.variables,
            max_turns=payload.max_turns,
            clear_inquiry_type=payload.clear_inquiry_type,
        )
        merged = state.get("merged", {}) or {}
        turns = state.get("turns", []) or []
        per_type_count = sum(
            1 for t in turns if isinstance(t, dict) and t.get("inquiry_type") == payload.inquiry_type
        )
        response_payload = ConversationVariablesUpsertResponse(
            inquiry_type=payload.inquiry_type,
            variables=merged.get(payload.inquiry_type, {}) or {},
            turn_count_total=len(turns),
            turn_count_for_inquiry_type=per_type_count,
            max_turns=payload.max_turns,
        )
    except HTTPException as http_exc:
        response_status = http_exc.status_code
        error_message = str(http_exc.detail)
        # Continue to log, then re-raise after the audit row is written.
        _http_exc_to_reraise: HTTPException | None = http_exc
    except Exception as exc:
        logger.exception("conversation-variables upsert failed: %s", exc)
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = "Failed to upsert conversation variables."
        _http_exc_to_reraise = HTTPException(
            status_code=response_status,
            detail=error_message,
        )
    else:
        _http_exc_to_reraise = None

    # Always log to integration_logs so debugging variable-extraction regressions has an audit trail.
    try:
        request_headers = dict(request.headers)
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="respond_contacts.session_vars",
                business_id=str(uuid.uuid4()),
                external_reference=f"{payload.contact_id}:{payload.space_id}:{payload.inquiry_type}",
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
            "Failed to create integration log for conversation-variables upsert: %s",
            log_error,
            exc_info=True,
        )

    if _http_exc_to_reraise is not None:
        raise _http_exc_to_reraise

    assert response_payload is not None  # for type-checkers; success path always sets this
    return response_payload
