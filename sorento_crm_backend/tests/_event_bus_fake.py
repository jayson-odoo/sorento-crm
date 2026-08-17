"""An in-memory stand-in for the conversation event bus's Redis transport.

The bus is a poke pipe, so its tests are about routing and lifecycle, not about
Redis: a fake transport makes "was this published", "did the subscriber get it"
and "was the subscription released" directly observable, with no broker to be
up and no sleeps to guess at. One live-Redis test exists separately
(``test_conversation_event_bus_redis.py``), skipped when REDIS_URL is not
reachable, so the real transport is not asserted purely by hope.

Deliberately deque-based rather than ``asyncio.Queue``: a publish happens on
whatever thread the request handler runs on (TestClient uses a worker thread),
while the subscriber lives on the event loop, and ``Queue.put_nowait`` across
that boundary is not safe.
"""
from __future__ import annotations

import asyncio
from collections import deque


class FakeSubscription:
    """One subscriber's mailbox. Registered on enter, released on exit."""

    def __init__(self, transport: "FakeEventTransport", channel: str):
        self._transport = transport
        self.channel = channel
        self._inbox: deque[str] = deque()

    async def __aenter__(self) -> "FakeSubscription":
        self._transport.subscriptions.append(self)
        return self

    async def __aexit__(self, *_exc) -> bool:
        try:
            self._transport.subscriptions.remove(self)
        except ValueError:  # already released
            pass
        return False

    def deliver(self, payload: str) -> None:
        self._inbox.append(payload)

    async def next_event(self, timeout: float) -> str | None:
        """The next raw payload, or None once ``timeout`` seconds pass."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if self._inbox:
                return self._inbox.popleft()
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(0.005)


class FakeEventTransport:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.published: list[tuple[str, str]] = []
        self.subscriptions: list[FakeSubscription] = []

    # -- publisher side ----------------------------------------------------
    def publish(self, channel: str, payload: str) -> None:
        if self.fail:
            raise RuntimeError("simulated Redis outage")
        self.published.append((channel, payload))
        for subscription in list(self.subscriptions):
            if subscription.channel == channel:
                subscription.deliver(payload)

    # -- subscriber side ---------------------------------------------------
    def subscribe(self, channel: str) -> FakeSubscription:
        return FakeSubscription(self, channel)

    # -- assertions --------------------------------------------------------
    @property
    def active_subscriptions(self) -> int:
        return len(self.subscriptions)

    def payloads(self) -> list[dict]:
        import json

        return [json.loads(payload) for _channel, payload in self.published]
