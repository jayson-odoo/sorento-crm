"""External API: the chatbot turn endpoint (D4, D9, D14, D15).

`POST /api/v1/external/chat/turn` runs one turn and RETURNS the result; the CALLER sends.
That is deliberate and was the owner's own revision at review round 3: a fixed CRM-to-n8n
URL would decide egress on the CRM side, so a chat-console or clone turn would push to the
live sender. Returning the data keeps egress with whoever called and keeps the test
harness's containment model intact. n8n already waits the whole turn today, so nothing
gets slower.

This module is one of only three files allowed to import `app.services.chatbot`
(`tests/chatbot/test_import_boundary.py` enforces it; the others are the trace/admin API
and the RQ task the offload runs on). It is a thin adapter: validate, call `run_turn`,
serialise, log. Every call writes an `integration_log` on success AND failure, the same as
the ideation turn and the conversation-variables endpoint.

**In S7 mode (`CHATBOT_ORDERING_ENABLED`) `/turn` is the only trigger**: it runs the whole
turn, orders it per contact, and returns the finished reply and actions, so `/complete`
answers 410 Gone. The route is still declared because n8n keeps calling it until the S7
promote lands on the n8n side; it is deleted at S8 (H6, AC-701).

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
from app.config import settings
from app.database import SessionLocal, get_db
from app.models.chatbot_turn import ChatbotTurn
from app.dependencies import get_external_api_user
from app.schemas.integration import IntegrationLogCreate
from app.services.chatbot import complete_turn, run_turn
# The head's OWN lookup for "which row is this message's turn" (D15), so the id-less
# complete route and the duplicate-delivery check can never pick different rows.
from app.services.chatbot.engine import find_turn_for_message
from app.services.error_handler import AppException
from app.services.chatbot_reply_copy import CHATBOT_TURN_ERROR_REPLY
from app.services.chatbot.contracts import (
    CompleteRequest,
    CompleteResponse,
    TurnRequest,
    TurnResponse,
)
from app.services.error_handler import AppException
from app.services.integration_service import IntegrationLogService

logger = logging.getLogger(__name__)
router = APIRouter()

# A real turn is a WhatsApp message plus a session blob: a few KB, and the largest capture
# in the 1,535-fixture corpus is well under one hundred. 256 KB is therefore three orders
# of magnitude of headroom AND a bound on what one caller can push into `chatbot.turns`,
# which is written once per customer message and never pruned.
#
# Measured on the PARSED payload, not on `content-length`. Two reasons, and both were
# defects in the first version:
#
# * a chunked request carries no `content-length` at all, so a header check is skippable
#   by the caller - exactly the caller a size guard exists for;
# * by the time this route function runs FastAPI has already read, parsed and validated
#   the body into `TurnRequest` (that is what resolving the `payload` parameter does), so
#   the guard cannot protect the parse however it is measured. What it CAN bound is the
#   write: `chatbot.turns` keeps the envelope, is written once per customer message and is
#   never pruned, and the integration log copies it. STORED is the honest claim.
#
# Bounding the socket read is a server-level concern (`client_max_body_size`), and saying
# so is better than implying a protection this cannot give.
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

# What the customer reads when the tail could not finish. The SAME declaration the head's
# parser reads, in a core module the package does not own, so the two can never drift
# into two different apologies for the same silence and the package keeps exporting
# exactly its two entry points (D3).
TAIL_ERROR_REPLY = CHATBOT_TURN_ERROR_REPLY


# H6, AC-701: the thin spine has ONE trigger. In S7 mode `/turn` runs the whole turn and
# returns the finished reply, so a caller arriving at `/complete` is running the pre-S7
# graph against an S7 backend - it has a turn the CRM already answered and is about to
# answer it a second time. 410 rather than 404: the route existed, it is gone on purpose,
# and n8n's error branch shows the operator which half of the promote was missed.
#
# The ROUTE itself is deleted at S8, not here. n8n's S2 tail keeps calling `/complete`
# until the S7 promote lands on the n8n side, and deleting the route before that strands
# every turn a lane still completes (n8n-changes.md, S7).
S7_TAIL_GONE_CODE = "CHATBOT_S7_MODE_OWNS_THE_TAIL"
S7_TAIL_GONE_MESSAGE = (
    "This turn was already completed by the CRM. S7 mode owns the tail: POST /chat/turn "
    "runs the whole turn and returns the finished reply and actions, so there is nothing "
    "left for /complete to fold in."
)


def _s7_mode() -> bool:
    """`CHATBOT_ORDERING_ENABLED` - the one flag that says the CRM owns the whole turn.

    It is the same flag that turns per-contact ordering on because they are the same
    promote: the thin spine posts every message to `/turn`, the CRM orders them per
    contact and answers each one itself. Two flags for one cutover would only let an
    operator half-arrive.
    """
    return bool(getattr(settings, "chatbot_ordering_enabled", False))


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
        # The serialised payload, so a chunked request with no `content-length` is bounded
        # too. See MAX_TURN_BODY_BYTES: this is a bound on what gets STORED.
        body_bytes = len(payload.model_dump_json().encode("utf-8"))
        if body_bytes > MAX_TURN_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"The turn body is {body_bytes} bytes, over the "
                    f"{MAX_TURN_BODY_BYTES} byte limit. A turn carries one message and the "
                    "session state, not an attachment - send media by reference."
                ),
            )
        # The auth dependencies queried on THIS session and neither committed nor rolled
        # back, so SQLAlchemy is holding their transaction - and with it one server
        # connection out of PgBouncer's transaction-mode pool - for as long as the request
        # runs. That is the whole turn: the parser call, the lookups, and (with ordering
        # on) up to `chatbot_queue_wait_seconds` of waiting on top. At the burst this
        # slice is built for, 100 concurrent turns would pin 100 connections from a pool
        # of 50 before the engine has opened a single session of its own.
        #
        # One rollback ends it. Nothing above needs the transaction any more - the
        # principal and its permission were read into plain dicts - and the integration
        # log below simply begins a new one. `db.info` (the company scope `get_db` set)
        # is session state, not transaction state, and survives.
        db.rollback()
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


def _turn_row(db: Session, turn_id: str) -> ChatbotTurn | None:
    """The turn row, read through the REQUEST session, for the two facts the route needs
    that the engine's answer cannot carry: `is_test` on a tail that raised.

    Kept to one query and one place. `turn_id` comes off the path (or the resolver) and a
    malformed one is a miss, not a 500 - the caller already has its 404 for that.
    """
    try:
        return db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    except Exception:  # noqa: BLE001 - a bad id is a miss, and the answer is already decided
        db.rollback()
        return None


def _log_complete_call(
    db: Session,
    *,
    request: Request,
    payload: CompleteRequest,
    business_id: str,
    external_reference: str,
    status_code: int,
    error_message: str | None,
) -> None:
    """The `integration_log` row every `/complete` call writes, answered or refused.

    ONE writer for both complete routes and for both outcomes, because the module contract
    is that no call to this endpoint is invisible - a 404 or a 409 on the id-less form is
    exactly the call an operator reading an n8n run needs to find, and it used to be the
    only one that left no trace.

    Best-effort, like every other post-response side effect here: the answer has already
    been decided and failing to describe it must not change it.
    """
    try:
        request_headers = dict(request.headers)
        if "x-api-key" in request_headers:
            request_headers["x-api-key"] = "***"
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="chatbot.turns",
                business_id=business_id,
                external_reference=external_reference,
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
    except Exception as log_error:  # noqa: BLE001
        logger.warning(
            "Failed to create integration log for chatbot turn completion: %s",
            log_error,
            exc_info=True,
        )


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
        if _s7_mode():
            raise AppException(
                status_code=status.HTTP_410_GONE,
                message="This turn engine completes its own turns.",
                detail=S7_TAIL_GONE_MESSAGE,
                code=S7_TAIL_GONE_CODE,
            )
        # Same reason as `/turn`: end the auth dependencies' transaction before the tail
        # runs, so the request is not pinning a pooled connection across it.
        db.rollback()
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
        # `AppException` is an `HTTPException`, so the engine's 409 for a turn that never
        # delegated arrives here already carrying its own status and reason.
        response_status = http_exc.status_code
        error_message = str(http_exc.detail)
        to_reraise = http_exc
    except Exception as exc:  # noqa: BLE001 - a failed tail is an ANSWERED call
        # The engine has already closed the turn `failed` at `remembered` with the reason
        # on the row and the trace. What the CALLER needs from here is the same thing the
        # head gives it on a failed parse (AC-105): today's error reply to send, as an
        # action, so the customer is answered rather than left silent. A 500 would leave
        # n8n with nothing to send and the customer with nothing at all - and the failure
        # is not lost, it is on `chatbot.turns` and in the integration log below.
        logger.exception("chatbot turn %s failed to complete: %s", turn_id, exc)
        error_message = f"{type(exc).__name__}: {exc}"
        # The row's own `is_test`, read back rather than assumed: a clone turn's failure
        # reply must carry `dry_run` too, or the one action this answer has is the one
        # action a test envelope could actually send. A row that has gone (pruned mid
        # turn) reads as a live turn, which is the safe direction for a `dry_run` FLAG and
        # the wrong direction for nothing else here.
        row = _turn_row(db, turn_id)
        dry_run = bool(getattr(row, "is_test", False))
        reply = {
            "text": TAIL_ERROR_REPLY,
            "quick_replies": None,
            "result_set": None,
            "attachments_src": None,
        }
        response_payload = CompleteResponse(
            turn_id=turn_id,
            reply=reply,
            # NEVER a null reply and never an empty `actions`: the caller executes
            # `actions` and nothing else (the executor ruling, 5 Sep), so an answer whose
            # words are only on `reply.text` is a customer left in silence. Same four keys
            # `_send_actions` emits, so the sender reads one shape on every turn.
            actions=[
                {
                    "kind": "send_message",
                    "text": TAIL_ERROR_REPLY,
                    "quick_replies": None,
                    "result_set": None,
                    "dry_run": dry_run,
                }
            ],
            is_test=dry_run,
        )

    _log_complete_call(
        db,
        request=request,
        payload=payload,
        business_id=turn_id,
        external_reference=turn_id,
        status_code=response_status,
        error_message=error_message,
    )

    if to_reraise is not None:
        raise to_reraise

    assert response_payload is not None
    return response_payload


def _resolve_turn_for_complete(db: Session, payload: CompleteRequest) -> str:
    """Find the turn a body describes, without an id in the path.

    Agreed with the n8n side so their cut touches ONE workflow: `sub-output` has the `ctx`
    but not the turn id (the id lives on the spine, two workflows up), and threading it
    through would mean editing the spine, `sub-main-processing` and every
    `Call 'sub-output'*` caller. The pair `(contact, respond message id)` already
    identifies the turn - it is the same pair `chatbot.turns` is UNIQUE on (D15) - so the
    body it already sends is enough.

    **The HIGHEST attempt wins, and it is the SAME row the engine calls "this turn".**
    `find_turn_for_message` is the head's own duplicate lookup (D15), reused here rather
    than re-implemented: a retry from the trace screen (R4, S2b) inserts another row for
    the same message, and completing the first one would fold the lane's result into the
    attempt nobody is watching. Two readers of one pair that ordered their rows differently
    would disagree about which row IS the turn the moment a second one existed, so there is
    one helper and one answer.
    """
    ctx = payload.ctx or {}
    contact_id = ((ctx.get("contact") or {}).get("id"))
    # `ctx.text` IS `tf-message`'s own item, so the respond message id sits at
    # `ctx.text.message.messageId` - one level up from the message BODY
    # (`ctx.text.message.message.text`), which is the level that reads like the obvious
    # one and is wrong.
    message = (ctx.get("text") or {}).get("message") or {}
    message_id = message.get("messageId")
    if contact_id in (None, "") or message_id in (None, ""):
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="This turn could not be identified.",
            detail=(
                "the body carries no `ctx.contact.id` / `ctx.text.message.messageId` pair, "
                "which is what identifies a turn when the path has no id"
            ),
            code="CHATBOT_TURN_NOT_IDENTIFIED",
        )

    row = find_turn_for_message(
        db, contact_respond_id=str(contact_id), message_id=str(message_id)
    )
    if row is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="This turn could not be found.",
            detail=(
                f"no chatbot turn for contact {contact_id} and message {message_id}: the "
                "head either never ran for it or the row has been pruned"
            ),
            code="CHATBOT_TURN_NOT_FOUND",
        )
    # `done` WITH a stored response is not a refusal: it is the replay `complete_turn`
    # already answers a duplicate delivery with (the tail ran, the caller has its answer
    # and must not send it twice), and refusing it here would have made that branch
    # unreachable from the route n8n actually calls. Everything else - `processing`,
    # `failed`, or a `done` row with nothing stored - has no lane result to fold in and no
    # answer to replay, so it is refused BEFORE the tail runs: completing it would compose
    # an answer out of the caller's fragments and erase the failure record.
    replayable = row.status == "done" and isinstance(row.response, dict)
    if row.status != "delegated" and not replayable:
        raise AppException(
            status_code=409,
            message="This turn cannot be completed.",
            detail=(
                f"chatbot turn {row.id} is {row.status!r} at stage {row.stage!r}: it is "
                "neither 'delegated' (a lane result to fold in) nor a finished turn with a "
                "stored answer to replay. A failed turn is retried from the trace screen, "
                "never completed."
            ),
            code="CHATBOT_TURN_NOT_DELEGATED",
        )
    return str(row.id)


@router.post("/turn/complete", response_model=CompleteResponse, status_code=status.HTTP_200_OK)
def chat_turn_complete_by_body(
    payload: CompleteRequest,
    request: Request,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """`/turn/{id}/complete` without the id: the body says which turn it is.

    Same request body, same response, same engine call. The ONLY difference is how the
    turn is found, and the reason is the n8n side's: `sub-output` holds the `ctx` and not
    the id, so this keeps their cut inside one workflow.
    """
    try:
        turn_id = _resolve_turn_for_complete(db, payload)
    except AppException as refused:
        # A refusal is a call too. Logged here because the answer is decided BEFORE
        # `chat_turn_complete` runs, so its own log would never be reached, and a 404 /
        # 409 that leaves no `integration_log` row is the one call an operator cannot
        # find when n8n reports a turn that was never finished.
        detail = refused.detail if isinstance(refused.detail, dict) else {}
        ctx = payload.ctx or {}
        _log_complete_call(
            db,
            request=request,
            payload=payload,
            business_id=str(uuid.uuid4()),
            external_reference=str((ctx.get("contact") or {}).get("id") or ""),
            status_code=refused.status_code,
            error_message=str(detail.get("detail") or detail.get("message") or refused.detail),
        )
        raise
    return chat_turn_complete(turn_id, payload, request, current_user, db)
