"""External API: the chatbot turn endpoint (D4, D9, D14, D15).

`POST /api/v1/external/chat/turn` runs one turn and RETURNS the result; the CALLER sends.
That is deliberate and was the owner's own revision at review round 3: a fixed CRM-to-n8n
URL would decide egress on the CRM side, so a chat-console or clone turn would push to the
live sender. Returning the data keeps egress with whoever called and keeps the test
harness's containment model intact. n8n already waits the whole turn today, so nothing
gets slower.

This module is one of only two files allowed to import `app.services.chatbot`
(`tests/chatbot/test_import_boundary.py` enforces it). It is a thin adapter: validate,
call `run_turn`, serialise, log. Every call writes an `integration_log` on success AND
failure, the same as the ideation turn and the conversation-variables endpoint.

**`SessionLocal` here is the engine's session seam, and it is the ONLY one.** The engine
opens and closes its own sessions around the LLM call (the capacity rule: never hold one
across provider I/O), so it cannot use the request's `Depends(get_db)` session - the
module-level name below is what it gets instead. Two consequences, both load-bearing:

* it must stay a MODULE-LEVEL name. Inlining it (`session_factory=app.database.SessionLocal`)
  would leave nothing to patch, and every endpoint test would silently start writing to
  the shared prod-copy database instead of a scratch schema. `tests/chatbot/
  test_chat_turn_endpoint.py` guards the shape;
* a test that exercises this endpoint patches `app.api.v1.external.chat.SessionLocal`,
  and patching only `Depends(get_db)` is not enough - `is_test` suppresses WRITES, not
  the connection.
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

# The engine's session seam. See the module docstring: module-level on purpose, and
# the single point every test patches to keep the engine off the shared database.
from app.database import SessionLocal, get_db
from app.dependencies import get_external_api_user
from app.schemas.integration import IntegrationLogCreate
from app.services.chatbot import complete_turn, run_turn
from app.services.chatbot.contracts import (
    CompleteRequest,
    CompleteResponse,
    TurnRequest,
    TurnResponse,
)
from app.services.integration_service import IntegrationLogService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/turn", response_model=TurnResponse, status_code=status.HTTP_200_OK)
def chat_turn(
    payload: TurnRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Run the head of one turn and return `{turn_id, ctx, item, branch_kind, delegate}`.

    `db` here is the REQUEST session and is used only for the integration log. The engine
    opens and closes its own sessions around the LLM call (the plan's capacity rule: never
    hold a session across provider I/O), which is why it takes `SessionLocal` rather than
    this one.
    """
    _ = current_user

    response_status = status.HTTP_200_OK
    error_message: str | None = None
    response_payload: TurnResponse | None = None
    to_reraise: HTTPException | None = None

    try:
        result = run_turn(payload.envelope, session_factory=SessionLocal)
        response_payload = TurnResponse(**result.as_dict())
        if result.status == "failed":
            # A failed TURN is still a successful CALL: the caller gets the error reply to
            # send and the failure is recorded on the row and the trace (R4, no auto retry).
            error_message = result.error
    except HTTPException as http_exc:
        response_status = http_exc.status_code
        error_message = str(http_exc.detail)
        to_reraise = http_exc
    except Exception as exc:  # noqa: BLE001 - log then surface a clean 500
        logger.exception("chatbot turn failed: %s", exc)
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = "Failed to handle chatbot turn."
        to_reraise = HTTPException(status_code=response_status, detail=error_message)

    try:
        request_headers = dict(request.headers)
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="chatbot.turns",
                business_id=(response_payload.turn_id if response_payload else str(uuid.uuid4())),
                external_reference=str(payload.envelope.contact.get("id") or ""),
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
    except Exception as log_error:  # noqa: BLE001
        logger.warning(
            "Failed to create integration log for chatbot turn: %s", log_error, exc_info=True
        )

    if to_reraise is not None:
        raise to_reraise

    assert response_payload is not None
    return response_payload


@router.post(
    "/turn/{turn_id}/complete",
    response_model=CompleteResponse,
    status_code=status.HTTP_200_OK,
)
def chat_turn_complete(
    turn_id: str,
    payload: CompleteRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Run the tail of a delegated turn and return `{reply, actions}` (AC-201).

    The lane ran in n8n and handed back what it built; everything from build-outcome to
    the session write happens here, and after this ships the CRM is the ONLY writer of
    `respond_contacts.session_vars` on the turn path (D2, AC-207).

    Same session seam as `/turn`: the engine takes `SessionLocal` because it opens and
    closes its own sessions (and, from S2, makes a roster read between them), while `db`
    is the request session and is used only for the integration log.
    """
    _ = current_user

    response_status = status.HTTP_200_OK
    error_message: str | None = None
    response_payload: CompleteResponse | None = None
    to_reraise: HTTPException | None = None

    try:
        result = complete_turn(
            turn_id,
            payload.model_dump(mode="json"),
            session_factory=SessionLocal,
        )
        response_payload = CompleteResponse(**result.as_dict())
    except LookupError as missing:
        # An unknown turn id is the caller pointing at a turn that never existed (or was
        # pruned), not an outage. 404 says which, so the operator reading the n8n run
        # does not go looking for a backend fault.
        response_status = status.HTTP_404_NOT_FOUND
        error_message = str(missing)
        to_reraise = HTTPException(status_code=response_status, detail=error_message)
    except HTTPException as http_exc:
        response_status = http_exc.status_code
        error_message = str(http_exc.detail)
        to_reraise = http_exc
    except Exception as exc:  # noqa: BLE001 - log then surface a clean 500
        logger.exception("chatbot turn %s failed to complete: %s", turn_id, exc)
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = "Failed to complete chatbot turn."
        to_reraise = HTTPException(status_code=response_status, detail=error_message)

    try:
        request_headers = dict(request.headers)
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="chatbot.turns",
                business_id=turn_id,
                external_reference=turn_id,
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
    except Exception as log_error:  # noqa: BLE001
        logger.warning(
            "Failed to create integration log for chatbot turn completion: %s",
            log_error,
            exc_info=True,
        )

    if to_reraise is not None:
        raise to_reraise

    assert response_payload is not None
    return response_payload
