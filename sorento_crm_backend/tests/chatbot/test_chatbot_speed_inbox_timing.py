"""CHATBOT-SPEED: an inbox turn stores where its time outside the engine went.

Crew's stage timings (12 Nov): on the inbox path about 0.55 s p50 of each turn sits outside every stage
("unaccounted"), and the queue wait before the claim is not stored at all. The drain now appends one `inbox` trace
event per turn: `queued_ms` (stored -> claimed), `lookup_ms` (the respond.io takeover check before the engine),
`send_ms` (the sender POST, every attempt) and `send_attempts`. Measurement only: nothing a customer sees changes.
"""
from __future__ import annotations

import time
from typing import Any

from app.services.chatbot import direct_ingress
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    assert_nothing_to_send,
    iq_serial,
    redis_client,
    world,
)


def _finished_row(world, contact: str, mid: int, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = world.row_for(contact, mid)
        if row is not None and row["status"] in ("done", "failed"):
            return row
        time.sleep(0.05)
    raise AssertionError(f"turn never finished: {world.row_for(contact, mid)!r}")


def _inbox_events(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in row["trace"] if isinstance(e, dict) and e.get("kind") == "inbox"]


def _drain_one(world, label: str) -> dict[str, Any]:
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 20, label)
    queued, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(queued)
    world.wait_posts(1, contact)
    return _finished_row(world, contact, mid)


def test_a_drained_turn_stores_one_inbox_timing_event(world):
    row = _drain_one(world, "time1")
    events = _inbox_events(row)
    assert len(events) == 1, [(e.get("kind"), e.get("stage")) for e in row["trace"]] + [row["status"], row["stage"]]
    event = events[0]
    for key in ("queued_ms", "lookup_ms", "send_ms"):
        assert isinstance(event.get(key), int) and event[key] >= 0, event
    assert event.get("send_attempts") == 1, event


def test_the_send_time_is_the_sender_post(world):
    world.post_delay = 0.3
    event = _inbox_events(_drain_one(world, "time2"))[0]
    assert event["send_ms"] >= 300, event


def test_the_lookup_time_is_the_takeover_check(world, monkeypatch):
    fake = direct_ingress._lookup_contact  # the world's fake

    def slow(db, contact_id):
        time.sleep(0.2)
        return fake(db, contact_id)

    monkeypatch.setattr(direct_ingress, "_lookup_contact", slow)
    event = _inbox_events(_drain_one(world, "time3"))[0]
    assert event["lookup_ms"] >= 200, event
