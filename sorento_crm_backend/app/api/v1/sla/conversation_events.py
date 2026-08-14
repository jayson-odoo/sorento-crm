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


async def _stream_principal(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Authenticate, then hand the pooled DB connection straight back.

    A streaming response finishes only when the client disconnects, and
    FastAPI tears yield-dependencies down after that - so depending on ``get_db``
    normally would pin one pooled connection per open drawer for as long as the
    tab stays open (pool is 10 + 20 overflow). The stream itself reads no
    database: it forwards pokes, and the subscriber refetches through the
    ordinary REST API. Closing here is safe and idempotent - ``get_db``'s own
    finally still runs.
    """
    try:
        if db is not None:
            db.close()
    except Exception:  # noqa: BLE001 - releasing early is an optimisation
        logger.debug("stream principal: early session close failed", exc_info=True)
    return current_user


def _frame(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.get("/stream")
async def stream_conversation_events(
    contacts: Optional[str] = Query(
        None,
        description="Comma-separated Respond.io contact ids whose thread events this "
        "client wants (the drawer passes the contact it has open).",
    ),
    current_user: dict = Depends(_stream_principal),
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
    the contacts it explicitly named in ``?contacts=`` (the open drawer). It
    never sees the rest of the workspace's traffic.

    Stateless by design - no Last-Event-ID, no replay. A reconnect simply
    resubscribes, and anything published while the socket was down is covered by
    the FE refetching on the ``ready`` frame plus the drawer's 10s poll fallback
    (shipped in D4). Missing an event therefore costs latency, never a wrong
    screen, which is why the transport is allowed to be lossy pub/sub.

    Emits a ``ready`` event on connect (refetch cue) and a comment heartbeat
    every 25s so proxies do not reap the idle connection. Closing the client
    releases the subscription in the generator's finally.
    """
    user_id = str(current_user.get("id") or "")
    contact_ids = _parse_contacts(contacts)
    if len(contact_ids) > MAX_CONTACTS:
        contact_ids = set(list(sorted(contact_ids))[:MAX_CONTACTS])

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
