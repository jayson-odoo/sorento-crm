"""AC-713: a poller batch and a live webhook message for one contact keep their order.

This exists NEXT TO `test_s7_ordering_and_offload.py::TestPollerBatchAndLiveMessageKeepOrder`
rather than instead of it. That test asserts the same behaviour and cannot pass as written:
its `stub_engine_seams` fixture stubs `resolve_config` and `check_access` but not
`parser.parse`, so all six turns make a real provider call with the fixture's `sk-test` key,
come back 401, and land on `failed` before the ordering assertions are reached. Its ordering
half (elapsed, and the `seq` / `done` counters) does pass. The tester owns that file, so the
one-line stub is reported rather than edited in, and the coverage lands here in the meantime.

Same shape as the tester's, with `parser.parse` stubbed the way the two ordering tests in
that file already stub it.
"""
from __future__ import annotations

import time

import pytest

from app.config import settings
from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_s7_ordering_and_offload import (  # noqa: F401 - fixtures by name
    _envelope_for,
    _redis_client,
    _done_key,
    _seq_key,
    real_contacts,
    redis_client,
    stub_engine_seams,
)
from tests.chatbot.test_engine import _parser_output


@pytest.fixture()
def _ordering_on(monkeypatch):
    monkeypatch.setattr(settings, "chatbot_ordering_enabled", True, raising=False)
    monkeypatch.setattr(settings, "chatbot_queue_wait_seconds", 5.0, raising=False)


def test_poller_batch_and_live_message_keep_order(
    real_contacts, stub_engine_seams, _ordering_on, monkeypatch
) -> None:
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: _parser_output())
    contact = real_contacts("batch-order-coder")

    ingresses = ["poller", "poller", "webhook", "poller", "poller", "poller"]
    started = time.monotonic()
    results = [
        engine_mod.run_turn(
            _envelope_for(contact, f"ZZT-msg-batch-coder-{i}", ingress=ingress),
            session_factory=SessionLocal,
        )
        for i, ingress in enumerate(ingresses, start=1)
    ]
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, (
        f"six sequential same-contact turns took {elapsed}s - something is waiting on a "
        "ticket that should already be free"
    )
    assert [r.status for r in results] == ["delegated"] * 6, [r.error for r in results]

    client = _redis_client()
    try:
        assert client.get(_seq_key(contact)) == "6"
        assert client.get(_done_key(contact)) == "6"
    finally:
        client.close()

    rows = (
        SessionLocal()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == contact)
        .all()
    )
    by_created = sorted(rows, key=lambda r: r.created_at)
    assert [r.ingress for r in by_created] == ingresses, (
        "trace rows must carry the ingress each turn actually arrived through, got "
        f"{[r.ingress for r in by_created]}"
    )
