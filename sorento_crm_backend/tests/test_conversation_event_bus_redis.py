"""The event bus against a REAL Redis, so the fake is not the only witness.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md (AC-K1)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S4.2)

Everything else in this slice runs on the in-memory transport, which proves the
routing but nothing about redis-py: that the async subscriber sees what the
sync publisher wrote, that ``get_message(timeout=...)`` returns None rather than
hanging, and that teardown releases the connection. This file pins exactly that
one seam, on a throwaway channel so it cannot collide with a running stack, and
skips itself when REDIS_URL is unreachable (CI without a broker).

Run:
    venv/bin/pytest tests/test_conversation_event_bus_redis.py -q
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.config import settings
from app.services import conversation_event_bus as bus


def _redis_reachable() -> bool:
    try:
        import redis as redis_sync

        client = redis_sync.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
        client.close()
        return True
    except Exception:  # noqa: BLE001 - no broker here, that is the answer
        return False


pytestmark = pytest.mark.skipif(
    not _redis_reachable(), reason=f"Redis not reachable at {settings.redis_url}"
)


@pytest.fixture
def scratch_channel(monkeypatch):
    """A channel nobody else is on, still under the shared namespace prefix."""
    name = f"{bus.CHANNEL_PREFIX}test-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(settings, "conversation_events_channel", name, raising=False)
    bus.set_transport(None)  # the real Redis transport
    yield name
    bus.set_transport(None)


@pytest.mark.asyncio
async def test_a_published_poke_reaches_a_live_subscriber(scratch_channel):
    transport = bus.get_transport()
    async with transport.subscribe(scratch_channel) as subscription:
        # Subscribe first: pub/sub has no backlog, an event published before the
        # subscription exists is gone. That is by design (a reconnecting client
        # refetches instead of replaying) and this ordering states it.
        bus.publish(bus.EVENT_MESSAGE, contact_id="10025904")

        raw = await subscription.next_event(timeout=3.0)

    assert raw is not None, "the live subscriber never saw the published poke"
    event = json.loads(raw)
    assert event["type"] == bus.EVENT_MESSAGE
    assert event["contact_id"] == "10025904"


@pytest.mark.asyncio
async def test_a_quiet_channel_ticks_instead_of_hanging(scratch_channel):
    """The heartbeat depends on this: no message within the poll window returns
    None, which is what lets the endpoint emit a keep-alive comment."""
    transport = bus.get_transport()
    async with transport.subscribe(scratch_channel) as subscription:
        assert await subscription.next_event(timeout=0.2) is None
