"""Server-sent events for the conversation ticket surfaces (UAC section K)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import conversation_event_bus as bus

logger = logging.getLogger(__name__)

router = APIRouter()

# A comment frame every this often. Long enough to be cheap, short enough to
# beat the usual 60s idle timeout on proxies and load balancers.
HEARTBEAT_SECONDS = 25.0
# How long one subscriber read waits before the loop gets a chance to heartbeat
# or notice the client is gone. Not a connection timeout.
POLL_SECONDS = bus.POLL_INTERVAL_SECONDS
# A client cannot pin an unbounded contact list on the server-side filter.
MAX_CONTACTS = 25


def _parse_contacts(raw: Optional[str]) -> set[str]:
    if not raw:
        return set()
    parts = [p.strip() for p in raw.split(",")]
    return {p for p in parts if p}


def entitled_contacts(db: Optional[Session], user_id: str, requested: set[str]) -> set[str]:
    """The subset of ``?contacts=`` the caller actually has standing for.

    ``?contacts=`` feeds the server-side filter, so taking it verbatim meant a
    client could name ANY Respond contact id - they are short numeric strings,
    so they are guessable - and be told live whenever that contact messages us.
    The frames carry no content, so this is a timing leak rather than a read,
    but "when is this person talking to Sorento" is not ours to hand out.

    Kept if the caller can act on at least one conversation ticket for the
    contact (which, per ``can_user_act_on_tracking``, covers their own tickets,
    their teams' and - after a resolve blanks the assignee - the ones they
    resolved). An admin keeps everything they asked for. Anything else is
    dropped SILENTLY: refusing the request would confirm which of the ids are
    real, and the drawer has nothing better to do with the error.

    Fails closed - no session, no contacts.
    """
    if not requested:
        return set()
    if db is None:
        logger.warning("conversation stream: no session to scope ?contacts= with")
        return set()

    from app.models.access import RespondContact
    from app.models.sla import ConversationSLATracking
    from app.services.sla_service import (
        ConversationSLATrackingService,
        conversation_tracking_scope,
    )

    service = ConversationSLATrackingService(db)
    if service._is_admin(user_id):
        return set(requested)

    rows = (
        db.query(ConversationSLATracking, RespondContact.respond_io_id)
        .join(
            RespondContact,
            RespondContact.id == ConversationSLATracking.respond_contact_id,
        )
        .filter(
            RespondContact.respond_io_id.in_(list(requested)),
            conversation_tracking_scope(),
        )
        .all()
    )
    allowed: set[str] = set()
    for tracking, respond_io_id in rows:
        rid = str(respond_io_id)
        if rid in allowed:
            continue
        if service.can_user_act_on_tracking(user_id, tracking):
            allowed.add(rid)
    return allowed


async def _stream_scope(
    contacts: Optional[str] = Query(
        None,
        description="Comma-separated Respond.io contact ids whose thread events this "
        "client wants (the drawer passes the contact it has open).",
    ),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[str, set[str]]:
    """Authenticate, resolve what this caller may listen to, then hand the
    pooled DB connection straight back.

    A streaming response finishes only when the client disconnects, and
    FastAPI tears yield-dependencies down after that - so holding ``get_db``
    for the life of the stream would pin one pooled connection per open drawer
    for as long as the tab stays open (pool is 10 + 20 overflow). The stream
    itself reads no database once it is running: it forwards pokes, and the
    subscriber refetches through the ordinary REST API. The one query that DOES
    need a session is the entitlement filter, which runs here, before the close.
    Closing is safe and idempotent - ``get_db``'s own finally still runs.
    """
    user_id = str(current_user.get("id") or "")
    requested = _parse_contacts(contacts)
    if len(requested) > MAX_CONTACTS:
        requested = set(sorted(requested)[:MAX_CONTACTS])
    try:
        allowed = entitled_contacts(db, user_id, requested)
    except Exception:  # noqa: BLE001 - fail closed, never 500 the stream
        logger.warning("conversation stream: contact scoping failed", exc_info=True)
        allowed = set()
    try:
        if db is not None:
            db.close()
    except Exception:  # noqa: BLE001 - releasing early is an optimisation
        logger.debug("stream scope: early session close failed", exc_info=True)
    return user_id, allowed


def _frame(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.get("/stream")
async def stream_conversation_events(
    scope: tuple[str, set[str]] = Depends(_stream_scope),
):
    """Live pokes for the ticket drawer and the pending-tasks worklist (AC-K1, K3).

    Each frame names WHAT changed and WHO it concerns, never the content::

        event: message
        data: {"type":"message","contact_id":"10025904","user_id":null,
               "entity_id":null,"ts":"2026-08-15T01:02:03.456789Z"}

    The client refetches through the normal permissioned REST endpoints on
    receipt. That is deliberate and is the whole idempotency story (AC-K4): a
    replayed or duplicated event costs one extra refetch and changes nothing on
    screen, so no sequencing, dedupe or replay buffer is needed on the wire.

    Filtering is server-side: a client receives events for its OWN user id plus
    the contacts it explicitly named in ``?contacts=`` (the open drawer) AND has
    ticket standing for (see ``entitled_contacts`` - a named id the caller
    cannot act on is dropped silently). It never sees the rest of the
    workspace's traffic.

    Stateless by design - no Last-Event-ID, no replay. A reconnect simply
    resubscribes, and anything published while the socket was down is covered by
    the FE refetching on the ``ready`` frame plus the drawer's 10s poll fallback
    (shipped in D4). Missing an event therefore costs latency, never a wrong
    screen, which is why the transport is allowed to be lossy pub/sub.

    Emits a ``ready`` event on connect (refetch cue) and a comment heartbeat
    every 25s so proxies do not reap the idle connection. Closing the client
    releases the subscription in the generator's finally.
    """
    user_id, contact_ids = scope

    async def event_stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        last_beat = loop.time()
        try:
            async with bus.subscribe() as subscription:
                yield _frame(
                    "ready",
                    {"type": "ready", "contacts": sorted(contact_ids)},
                )
                while True:
                    raw = await subscription.next_event(timeout=POLL_SECONDS)
                    if raw:
                        try:
                            event = json.loads(raw)
                        except Exception:  # noqa: BLE001 - a malformed poke is not fatal
                            logger.warning("conversation event: undecodable payload dropped")
                            event = None
                        if event and bus.event_matches(
                            event, user_id=user_id, contact_ids=contact_ids
                        ):
                            yield _frame(str(event.get("type") or "message"), event)
                            last_beat = loop.time()
                            continue
                    if loop.time() - last_beat >= HEARTBEAT_SECONDS:
                        # A comment frame: keeps proxies from reaping the
                        # connection and is ignored by EventSource.
                        yield ": keep-alive\n\n"
                        last_beat = loop.time()
        except asyncio.CancelledError:
            # The client went away. Nothing to report; the async-with above has
            # already released the subscription.
            raise
        except Exception:  # noqa: BLE001 - never take the process down with a stream
            logger.warning("conversation event stream failed", exc_info=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx: do not buffer, or every frame arrives in a batch at close.
            "X-Accel-Buffering": "no",
        },
    )
