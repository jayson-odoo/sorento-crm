"""Server push for the conversation ticket surfaces: a poke, never a payload.

UAC section K (documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md),
PLAN slice S4.2. The drawer must show an inbound WhatsApp message within seconds
(AC-K1) and the pending-tasks widget must reflect a new or changed ticket just as
fast (AC-K3), without either surface polling hard.

The shape, and why it is this shape
-----------------------------------
An event says only THAT something changed and WHO it concerns::

    {"type": "message", "contact_id": "10025904", "user_id": null,
     "entity_id": null, "ts": "2026-08-15T01:02:03.456789Z"}

It never carries message text, ticket fields, or anything else a permission
check would have to be re-run over. Subscribers refetch through the normal REST
API, which is where authorization, scoping and serialization already live. That
single decision is what makes AC-K4 (replayed / duplicated events) trivially
satisfied: two identical pokes cause two identical refetches and one identical
screen, so no dedupe table, no ordering guarantee and no sequence number is
needed anywhere.

Keys
----
``contact_id`` is the **Respond.io contact id** (``respond_contacts.respond_io_id``,
the same value ``chat_histories.contact_id`` stores and the same value the ticket
drawer already holds), NOT the internal ``respond_contacts.id`` UUID - those two
are different things in this codebase and confusing them is a standing bug
source (CLAUDE.md: "respond_contact_id != respond_io_id"). Publishers on the SLA
side resolve it from the tracking's contact; the chat ingest already receives it
verbatim, so nothing has to be looked up on the hot path.

``user_id`` is ``users.id`` of the person whose worklist changed.
``entity_id`` is the conversation-SLA tracking id when the event is about one
ticket (debugging and targeted refetch); it is null for message events, which
belong to a thread rather than to any single ticket.

Transport
---------
Redis pub/sub, so the API process, the RQ worker and the scheduler can all
publish and any API process can serve a subscriber. The channel is namespaced
(``sorento:conversation-events:v1``) because one Redis instance is shared by
every local worktree and by RQ.

Publishing is best-effort by contract: it runs AFTER the row is committed, so a
broker outage must degrade liveness (the FE's slow poll takes over) and never
turn a successful write into a 500 (PRINCIPLES.md, post-commit side effects).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

from app.config import settings

logger = logging.getLogger(__name__)

# Event types. Kept deliberately few: the subscriber decides what to refetch from
# the type, and every new type is a new FE branch.
EVENT_MESSAGE = "message"              # a chat_histories row landed for a contact
EVENT_TICKET_CREATED = "ticket_created"  # a new intervention ticket exists
EVENT_TICKET_UPDATED = "ticket_updated"  # clocks / assignee / resolution changed

EVENT_TYPES = frozenset({EVENT_MESSAGE, EVENT_TICKET_CREATED, EVENT_TICKET_UPDATED})

# Every channel this module uses starts here. Asserted by test, so a future
# channel cannot quietly land unnamespaced on the shared broker.
CHANNEL_PREFIX = "sorento:conversation-events:"

# How long a subscriber waits for a message before the caller gets a chance to
# emit a heartbeat. Not a timeout on the connection.
POLL_INTERVAL_SECONDS = 1.0


def channel() -> str:
    """The pub/sub channel, overridable per environment (CONVERSATION_EVENTS_CHANNEL)."""
    return getattr(settings, "conversation_events_channel", CHANNEL_PREFIX + "v1")


# --------------------------------------------------------------------------- #
# Transport                                                                     #
# --------------------------------------------------------------------------- #


class EventSubscription(Protocol):
    """An open subscription. Async context manager; releases on exit."""

    async def __aenter__(self) -> "EventSubscription": ...

    async def __aexit__(self, *exc) -> bool: ...

    async def next_event(self, timeout: float) -> Optional[str]:
        """The next raw payload, or None when ``timeout`` seconds pass with none."""
        ...


class EventTransport(Protocol):
    def publish(self, channel: str, payload: str) -> None: ...

    def subscribe(self, channel: str) -> EventSubscription: ...


class _RedisSubscription:
    """A Redis pub/sub subscription driven by the asyncio client.

    ``redis.asyncio`` is used rather than the synchronous client in a thread:
    the SSE endpoint runs on the event loop and a blocking ``get_message`` there
    would stall every other request in the process. ``get_message(timeout=...)``
    returns None on expiry, which is exactly the heartbeat tick the endpoint
    needs, so no separate timer is required.
    """

    def __init__(self, channel_name: str):
        self._channel = channel_name
        self._client = None
        self._pubsub = None

    async def __aenter__(self) -> "_RedisSubscription":
        import redis.asyncio as redis_asyncio

        self._client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self._channel)
        return self

    async def __aexit__(self, *_exc) -> bool:
        # Every step guarded: a client that disconnected mid-stream must still
        # release the rest, and teardown must not raise into the ASGI server.
        pubsub, client = self._pubsub, self._client
        self._pubsub = self._client = None
        for close in (
            lambda: pubsub.unsubscribe(self._channel),
            lambda: pubsub.aclose(),
            lambda: client.aclose(),
        ):
            try:
                if pubsub is None or client is None:
                    continue
                await close()
            except Exception:  # noqa: BLE001 - teardown is best-effort
                logger.debug("conversation event subscription teardown failed", exc_info=True)
        return False

    async def next_event(self, timeout: float) -> Optional[str]:
        """Wait up to ``timeout`` for one published payload.

        Loops rather than returning the first ``get_message`` result: redis-py
        answers None as soon as it consumes a control frame (the subscribe
        confirmation, a ping) even when the caller's timeout has not expired,
        so a single call drops the first real message of every connection -
        measured, not theorised. The deadline, not the call, owns the timeout.
        """
        import asyncio

        if self._pubsub is None:
            return None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            started = loop.time()
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=remaining
            )
            if message and message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, str):
                    return data
            if loop.time() - started < 0.005:
                # Returned instantly with nothing: yield rather than spin.
                await asyncio.sleep(0.005)


class RedisEventTransport:
    """The production transport. One lazily-built sync client for publishing."""

    def __init__(self):
        self._conn = None

    def _connection(self):
        if self._conn is None:
            import redis as redis_sync

            self._conn = redis_sync.from_url(settings.redis_url, decode_responses=True)
        return self._conn

    def publish(self, channel_name: str, payload: str) -> None:
        self._connection().publish(channel_name, payload)

    def subscribe(self, channel_name: str) -> EventSubscription:
        return _RedisSubscription(channel_name)


_transport: Optional[EventTransport] = None


def get_transport() -> EventTransport:
    global _transport
    if _transport is None:
        _transport = RedisEventTransport()
    return _transport


def set_transport(transport: Optional[EventTransport]) -> None:
    """Swap the transport. Test seam: pass None to restore the Redis one."""
    global _transport
    _transport = transport


# --------------------------------------------------------------------------- #
# Publishing                                                                    #
# --------------------------------------------------------------------------- #


def build_event(
    event_type: str,
    *,
    contact_id: Optional[str] = None,
    user_id: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict[str, Any]:
    """The full event envelope. Five keys, no content, ever."""
    return {
        "type": event_type,
        "contact_id": str(contact_id) if contact_id else None,
        "user_id": str(user_id) if user_id else None,
        "entity_id": str(entity_id) if entity_id else None,
        # Transport timestamp (UTC, explicit Z) - for debugging and for the FE to
        # ignore a stale frame after a reconnect. Not a domain datetime.
        "ts": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def publish(
    event_type: str,
    *,
    contact_id: Optional[str] = None,
    user_id: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> bool:
    """Poke every subscriber interested in this contact or this user.

    Returns True when the event went out. Never raises: callers are post-commit
    side effects, so the only honest failure mode is a degraded stream.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("conversation event: refusing unknown type %r", event_type)
        return False
    if not contact_id and not user_id:
        # Nothing could match it server-side, so it would be pure noise.
        logger.debug("conversation event: %s has no routing key, skipped", event_type)
        return False

    event = build_event(
        event_type, contact_id=contact_id, user_id=user_id, entity_id=entity_id
    )
    try:
        get_transport().publish(channel(), json.dumps(event))
        return True
    except Exception as e:  # noqa: BLE001 - liveness degrades, the write stands
        logger.warning(
            "conversation event: publish of %s failed (%s); the stream degrades to polling.",
            event_type,
            e,
        )
        return False


# --------------------------------------------------------------------------- #
# Subscribing                                                                   #
# --------------------------------------------------------------------------- #


def subscribe() -> EventSubscription:
    """An open subscription to the conversation channel (async context manager)."""
    return get_transport().subscribe(channel())


def event_matches(
    event: dict, *, user_id: Optional[str], contact_ids: Iterable[str]
) -> bool:
    """Server-side filter: is this client entitled to hear about this event?

    A client hears its OWN worklist events plus the contacts it explicitly has
    open (the drawer names them). Everything else is dropped before it leaves
    the process - a stream that fanned every event to every client would leak
    who is talking to whom and would scale with total traffic per connection.
    """
    if user_id and str(event.get("user_id") or "") == str(user_id):
        return True
    contact = str(event.get("contact_id") or "")
    return bool(contact) and contact in {str(c) for c in contact_ids}
