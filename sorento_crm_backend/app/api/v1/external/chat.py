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
from app.services.chatbot import run_turn
from app.services.chatbot.contracts import TurnRequest, TurnResponse
from app.services.integration_service import IntegrationLogService

logger = logging.getLogger(__name__)
router = APIRouter()

# A real turn is a WhatsApp message plus a session blob: a few KB, and the largest capture
# in the 1,535-fixture corpus is well under one hundred. 256 KB is therefore three orders
# of magnitude of headroom AND a bound on what one caller can push into `chatbot.turns`,
# which is written once per customer message and never pruned.
#
# Checked from `content-length`, which is what a body this size actually has: Starlette has
# already buffered the body by the time a route function runs, so this is a guard on what
# gets PARSED, VALIDATED and STORED, not on what gets read off the socket. Bounding the
# read is a server-level concern (`client_max_body_size`), and stating that here is better
# than implying a protection this cannot give.
MAX_TURN_BODY_BYTES = 256 * 1024

# The integration log records the CALL. A payload that was rejected for its size must not
# be copied into `integration_logs` in full - that would move the problem one table over.
MAX_LOGGED_PAYLOAD_BYTES = 64 * 1024


def _logged_payload(payload: TurnRequest) -> str:
    """The request body for the integration log, bounded."""
    body = payload.model_dump_json()
    if len(body) <= MAX_LOGGED_PAYLOAD_BYTES:
        return body
    return json.dumps(
        {
            "note": (
                f"payload omitted: {len(body)} bytes exceeds the "
                f"{MAX_LOGGED_PAYLOAD_BYTES} byte log cap"
            ),
            "contact_id": str(payload.envelope.contact.get("id") or ""),
        }
    )


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
        declared_bytes = int(request.headers.get("content-length") or 0)
        if declared_bytes > MAX_TURN_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"The turn body is {declared_bytes} bytes, over the "
                    f"{MAX_TURN_BODY_BYTES} byte limit. A turn carries one message and the "
                    "session state, not an attachment - send media by reference."
                ),
            )
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
                request_payload=_logged_payload(payload),
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
