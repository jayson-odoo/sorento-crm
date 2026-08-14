"""The conversation event bus: a poke, never a payload.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-K1 (an inbound message reaches an open drawer within seconds)
     AC-K3 (a ticket create / clock change reaches the pending-tasks widget)
     AC-K4 (a replayed or duplicated event is harmless)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S4.2)

AC-K4 is a property of the shape, not of a dedupe table: the event carries no
message content, only "something changed for this contact / this user", so the
subscriber refetches through the permissioned REST API. Two identical events
therefore produce two identical refetches and one identical screen.

Run:
    venv/bin/pytest tests/test_conversation_event_bus.py -q
"""
from __future__ import annotations

import json

import pytest

from app.services import conversation_event_bus as bus
from tests._event_bus_fake import FakeEventTransport

CONTACT = "10025904"
USER = "8f0f4e0e-0000-4000-8000-000000000001"
TRACKING = "4f0f4e0e-0000-4000-8000-0000000000aa"


@pytest.fixture
def transport():
    fake = FakeEventTransport()
    bus.set_transport(fake)
    try:
        yield fake
    finally:
        bus.set_transport(None)


def test_a_publish_puts_one_poke_on_the_namespaced_channel(transport):
    assert bus.publish(bus.EVENT_MESSAGE, contact_id=CONTACT) is True

    assert len(transport.published) == 1
    channel, raw = transport.published[0]
    assert channel == bus.channel()
    assert channel.startswith(bus.CHANNEL_PREFIX), (
        "Redis is shared across worktrees and workers; the channel must be namespaced"
    )
    assert json.loads(raw)["type"] == bus.EVENT_MESSAGE


def test_the_event_carries_no_message_content(transport):
    """The whole idempotency argument (AC-K4) rests on this: an event says
    THAT something changed, never WHAT was said. Anything else would have to be
    deduped, ordered and permission-checked on the wire."""
    bus.publish(
        bus.EVENT_TICKET_UPDATED,
        contact_id=CONTACT,
        user_id=USER,
        entity_id=TRACKING,
    )

    event = transport.payloads()[0]
    assert set(event) == {"type", "contact_id", "user_id", "entity_id", "ts"}
    assert event["contact_id"] == CONTACT
    assert event["user_id"] == USER
    assert event["entity_id"] == TRACKING
    assert isinstance(event["ts"], str) and event["ts"].endswith("Z")


def test_a_redis_outage_never_reaches_the_caller():
    """Publishing is a post-commit side effect: the ticket is already saved, so
    a broker outage must degrade the stream, never the write (PRINCIPLES.md)."""
    bus.set_transport(FakeEventTransport(fail=True))
    try:
        assert bus.publish(bus.EVENT_TICKET_CREATED, user_id=USER) is False
    finally:
        bus.set_transport(None)


def test_an_event_nobody_could_be_listening_for_is_not_published(transport):
    """No contact and no user means no subscriber can match it - publishing it
    is pure noise on a shared broker."""
    assert bus.publish(bus.EVENT_TICKET_UPDATED, entity_id=TRACKING) is False
    assert transport.published == []


def test_an_unknown_event_type_is_refused(transport):
    assert bus.publish("something_else", user_id=USER) is False
    assert transport.published == []


# --------------------------------------------------------------------------- #
# Server-side filtering: a client hears its own work, not everybody else's      #
# --------------------------------------------------------------------------- #


def _event(**kwargs) -> dict:
    return bus.build_event(kwargs.pop("event_type", bus.EVENT_TICKET_UPDATED), **kwargs)


def test_an_event_for_my_user_id_matches():
    assert bus.event_matches(_event(user_id=USER), user_id=USER, contact_ids=set())


def test_an_event_for_a_contact_i_have_open_matches():
    assert bus.event_matches(
        _event(contact_id=CONTACT), user_id=USER, contact_ids={CONTACT}
    )


def test_an_event_for_somebody_else_does_not_match():
    other = "8f0f4e0e-0000-4000-8000-000000000002"
    assert not bus.event_matches(
        _event(user_id=other, contact_id="999888777"),
        user_id=USER,
        contact_ids={CONTACT},
    )
