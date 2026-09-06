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
serialise, log. Every LIVE call writes an `integration_log` on success AND failure, the
same as the ideation turn and the conversation-variables endpoint - and a DRY RUN writes
none at all (H57, D14): the call log is business state an operator reads per customer, and
a test turn has nothing to say there that `chatbot.turns`' own `is_test` row does not
already carry.

**In S7 mode (`system_settings.chatbot_ordering_enabled`) `/turn` is the only trigger**: it runs the whole
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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

# The engine's session seam. See the module docstring: module-level on purpose, and
# the single point every test patches to keep the engine off the shared database.
from app.database import SessionLocal, get_db
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.dependencies import get_external_api_user
from app.schemas.chatbot_turn import ChatbotTurnResponse
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
from app.services.integration_service import (
    IntegrationLogService,
    sanitize_request_headers,
)

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


def _logged_payload(payload: BaseModel, *, reference: str = "") -> str:
    """The request body for the integration log, bounded.

    Takes ANY request model, because `/complete` needs the same bound and used to
    have none: `CompleteRequest` carries `item`, an optional `ctx` override and
    eleven producer fragments, one of which is a result set, and the engine's own
    document cap is 512 KB - so these are expected to get large, and the refusal
    path logs one too. Serialising it whole moved the problem `MAX_TURN_BODY_BYTES`
    exists to prevent one table over: unbounded rows in `integration_logs`.

    Over the cap the body is REPLACED by a note that names its size, the way
    `trace.cap_document` does it, rather than truncated to invalid JSON. The
    `reference` kept beside the note is whatever identifies the call - the contact
    on `/turn`, the turn id on `/complete` - so an operator reading the row can
    still find it.
    """
    body = payload.model_dump_json()
    if len(body) <= MAX_LOGGED_PAYLOAD_BYTES:
        return body
    return json.dumps(
        {
            "note": (
                f"payload omitted: {len(body)} bytes exceeds the "
                f"{MAX_LOGGED_PAYLOAD_BYTES} byte log cap"
            ),
            "reference": reference,
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


def _s7_mode(db: Session) -> bool:
    """`system_settings.chatbot_ordering_enabled` - the CRM owns the whole turn.

    It is the same switch that turns per-contact ordering on because they are the same
    promote: the thin spine posts every message to `/turn`, the CRM orders them per
    contact and answers each one itself. Two switches for one cutover would only let an
    operator half-arrive.

    A settings COLUMN since AC-810, read on the REQUEST session both callers already hold
    (no extra session, one query on the way to the 410) rather than from the environment,
    so the owner can turn it off from Settings > Chatbot and have the next call answer 200
    without a deploy - which is the whole point of the rollback path.
    """
    row = db.query(SystemSetting).first()
    return bool(getattr(row, "chatbot_ordering_enabled", False)) if row is not None else False


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

    # H57 / D14: a DRY RUN leaves no call log. `integration_log` is business state - it is
    # what an operator reads to answer "what did n8n send us about this customer?" - and a
    # row carrying a real contact id and the customer's message text, written because
    # somebody pressed Test on the Prompts screen, describes something that never happened
    # to that customer. The turn itself is not lost: `chatbot.turns` already holds this
    # turn's envelope, response and trace under `is_test = true`, which is strictly more
    # than this row would have carried. The LIVE path below is unchanged.
    if not payload.envelope.dry_run:
        try:
            request_headers = sanitize_request_headers(dict(request.headers))
            IntegrationLogService(db).create_integration_log(
                IntegrationLogCreate(
                    integration_channel="n8n",
                    business_table="chatbot.turns",
                    business_id=(
                        response_payload.turn_id if response_payload else str(uuid.uuid4())
                    ),
                    external_reference=str(payload.envelope.contact.get("id") or ""),
                    direction="inbound",
                    endpoint=str(request.url.path),
                    http_method=request.method,
                    request_headers=json.dumps(request_headers),
                    request_payload=_logged_payload(
                        payload, reference=str(payload.envelope.contact.get("id") or "")
                    ),
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


# --------------------------------------------------------------------------- #
# The Prompts screen's "Run a turn" test (AC-807)
# --------------------------------------------------------------------------- #

# The two prompt keys whose Test action runs a CHATBOT TURN rather than an assistant chat
# dry run. Neither is part of the assistant pipeline, so `AIAssistantChatService.respond`
# would have answered from prompts the operator did not edit - a result that looks like an
# answer and is a category error.
CHATBOT_PROMPT_KEYS = ("chatbot_semantic_parser", "chatbot_clarifier")


class DryRunTurnRefused(ValueError):
    """The request cannot be turned into a dry-run turn. The caller answers 422."""


def run_prompt_dry_run_turn(
    *, prompt_key: str, version_id: str, message: str, contact_respond_id: str | None
) -> dict:
    """One DRY-RUN turn on a pinned prompt version, for the Prompts screen (AC-807).

    **This function exists so `app/api/v1/system/ai_assistant.py` never imports
    `app.services.chatbot`.** AC-002 lists the files allowed through that boundary and the
    Prompts screen is not one of them - it is an assistant-settings surface that happens to
    want a chatbot turn. Putting the doorway HERE, in the file that already owns the turn
    endpoint, keeps the boundary at one file instead of widening the allow-list for a test
    button (`tests/chatbot/test_import_boundary.py` enforces it either way, so widening it
    would have been a decision recorded only in that list).

    `is_test=True`, so D14 applies with no exception: the engine writes `chatbot.turns` and
    nothing else - no session vars, no assignment, no send, no usage row. `prompt_overrides`
    is a harness key the engine reads ONLY on a dry run, which is what stops an unpublished
    prompt version ever reaching a customer.

    Returns `{turn_id, status, branch_kind, stage, trace, reply}`. The caller serialises it
    itself rather than through a `response_model`, because a declared model would silently
    drop whatever it does not know about and the trace is the whole point of the button.
    """
    contact = (contact_respond_id or "").strip()
    if not contact:
        raise DryRunTurnRefused(
            "contact_respond_id is required to run a chatbot turn: the turn reads that "
            "contact's access level and remembered state, and there is no meaningful "
            "default for it."
        )

    envelope = TurnRequest(
        envelope={
            "is_test": True,
            "ingress": "console",
            "contact": {"id": contact},
            "message": {
                "event_type": "message.received",
                "contact": {"id": contact},
                # A fresh id per test click, so two tests of the same message are two turns
                # rather than the second reading as a D15 duplicate of the first.
                "message": {
                    "messageId": f"prompt-test-{uuid.uuid4().hex[:16]}",
                    "contactId": contact,
                    "channelId": "prompt-test",
                    "traffic": "incoming",
                    "message": {"type": "text", "text": message},
                },
            },
            "prompt_overrides": {prompt_key: version_id},
        }
    ).envelope

    result = run_turn(envelope, session_factory=SessionLocal)
    payload = result.as_dict()

    # Status, stage and trace are read back from the ROW, not off the result: `TurnResult`
    # carries `status` only on the paths that need to TELL the caller something unusual
    # (failed, duplicate), so a turn that simply worked returns None there while the row
    # says `done`. The row is the record either way, and it is the same row the trace
    # screen renders, so the Test button and Chat History cannot disagree about a turn.
    status = payload.get("status")
    stage = payload.get("stage")
    trace: list = []
    turn: dict | None = None
    with SessionLocal() as db:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == payload["turn_id"]).first()
        if row is not None:
            status = row.status
            stage = row.stage
            trace = list(row.trace or [])
            # The WHOLE row, in the shape `GET /system/chatbot/turns` returns, so the
            # Prompts screen renders the result with Chat History's own `TurnPanel`
            # instead of a second trace viewer that would drift from it (journey D3: "the
            # same viewer the AI-assistant trace already uses").
            turn = json.loads(ChatbotTurnResponse.model_validate(row).model_dump_json())
    return {
        "turn_id": payload["turn_id"],
        "status": status,
        "branch_kind": payload.get("branch_kind"),
        "stage": stage,
        "reply": payload.get("reply"),
        "error": payload.get("error"),
        "trace": trace,
        "turn": turn,
    }


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
    dry_run: bool = False,
) -> None:
    """The `integration_log` row every LIVE `/complete` call writes, answered or refused.

    ONE writer for both complete routes and for both outcomes, because the module contract
    is that no live call to this endpoint is invisible - a 404 or a 409 on the id-less form
    is exactly the call an operator reading an n8n run needs to find, and it used to be the
    only one that left no trace.

    `dry_run` is H57 / D14, the same rule `/turn` follows above: a test turn writes nothing
    outside `chatbot.turns`, and the call log is outside it. Read off the turn ROW's own
    `is_test` rather than guessed, because the tail's caller sends no envelope.

    Best-effort, like every other post-response side effect here: the answer has already
    been decided and failing to describe it must not change it.
    """
    if dry_run:
        return
    try:
        request_headers = sanitize_request_headers(dict(request.headers))
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
                request_payload=_logged_payload(payload, reference=external_reference),
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
    # H57 / D14: is this a TEST turn? Only the ROW knows - the tail's caller sends no
    # envelope, and on the failure path below the answer is built here rather than read
    # off `complete_turn`. `None` means "not looked up yet", so the failure path's own
    # read is reused instead of paying for a second query on the way to the log.
    row_is_test: bool | None = None

    try:
        if _s7_mode(db):
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
        row_is_test = dry_run
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

    if row_is_test is None:
        row_is_test = bool(getattr(_turn_row(db, turn_id), "is_test", False))
    _log_complete_call(
        db,
        request=request,
        payload=payload,
        business_id=turn_id,
        external_reference=turn_id,
        status_code=response_status,
        error_message=error_message,
        dry_run=row_is_test,
    )

    if to_reraise is not None:
        raise to_reraise

    assert response_payload is not None
    return response_payload


def _body_turn_key(payload: CompleteRequest) -> tuple[Any, Any]:
    """`(contact id, respond message id)` out of an id-less `/complete` body.

    One reader, because two callers ask the same question: the resolver below turns the
    pair into a turn id, and the refusal path in `chat_turn_complete_by_body` needs the
    same pair to find out whether the turn it could not complete was a TEST turn (H57 -
    a refused call must not log a row a dry run is not allowed to write).

    `ctx.text` IS `tf-message`'s own item, so the respond message id sits at
    `ctx.text.message.messageId` - one level up from the message BODY
    (`ctx.text.message.message.text`), which is the level that reads like the obvious one
    and is wrong.
    """
    ctx = payload.ctx or {}
    message = (ctx.get("text") or {}).get("message") or {}
    return (ctx.get("contact") or {}).get("id"), message.get("messageId")


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
    contact_id, message_id = _body_turn_key(payload)
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

    **In S7 mode the 410 comes first, before the lookup.** Both forms of the route answer
    one cause, so they must answer it with one code: resolving the turn first lets a stale
    caller collect a 404 or a 409 on the way to a route that was going to say 410 anyway,
    which reads as three different faults instead of one missed promote. It also saves the
    two queries the lookup costs on every stale call.
    """
    try:
        if _s7_mode(db):
            raise AppException(
                status_code=status.HTTP_410_GONE,
                message="This turn engine completes its own turns.",
                detail=S7_TAIL_GONE_MESSAGE,
                code=S7_TAIL_GONE_CODE,
            )
        turn_id = _resolve_turn_for_complete(db, payload)
    except AppException as refused:
        # A refusal is a call too. Logged here because the answer is decided BEFORE
        # `chat_turn_complete` runs, so its own log would never be reached, and a 404 /
        # 409 that leaves no `integration_log` row is the one call an operator cannot
        # find when n8n reports a turn that was never finished.
        detail = refused.detail if isinstance(refused.detail, dict) else {}
        contact_id, message_id = _body_turn_key(payload)
        # H57: a refusal of a TEST turn is still a dry run, and a dry run writes nothing
        # outside `chatbot.turns`. Only the 409 arm can have a row behind it (the two 404s
        # are "no such turn"), so the lookup answers False by construction on those and
        # costs one query on a path that is already refusing.
        refused_row = (
            find_turn_for_message(
                db, contact_respond_id=str(contact_id), message_id=str(message_id)
            )
            if contact_id not in (None, "") and message_id not in (None, "")
            else None
        )
        _log_complete_call(
            db,
            request=request,
            payload=payload,
            business_id=str(uuid.uuid4()),
            external_reference=str(contact_id or ""),
            status_code=refused.status_code,
            error_message=str(detail.get("detail") or detail.get("message") or refused.detail),
            dry_run=bool(getattr(refused_row, "is_test", False)),
        )
        raise
    return chat_turn_complete(turn_id, payload, request, current_user, db)
