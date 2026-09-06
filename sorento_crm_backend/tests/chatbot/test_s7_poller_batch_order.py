"""AC-713 with the batch actually CONCURRENT: five poller messages plus one live webhook.

This exists NEXT TO `test_s7_ordering_and_offload.py::TestPollerBatchAndLiveMessageKeepOrder`
rather than instead of it, and the two halves are deliberately different. That one drives the
six turns sequentially, so it proves the fast path never stalls and the counters land at 6/6 -
worth keeping, and true by construction for the ordering half. This one fires all six at once,
50 ms apart, which is the shape AC-713 describes ("a live webhook message for the same contact
arrives mid-batch") and the only shape in which the ticket, the wait and the release are
exercised at all.

What it asserts is what the CRM guarantees: arrival order at the CRM, and no overlap. Both are
read back off `chatbot.turns` afterwards rather than from the client's own send order, because
the client fired the whole batch into six threads and cannot know which request the CRM took
first. The stagger is what makes arrival order equal send order.

Real Postgres and real redis, like the sibling file, for its reason: a single rollback-scoped
connection cannot show six threads racing.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.config import settings
from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_s7_ordering_and_offload import (  # noqa: F401 - fixtures by name
    _complete_in_the_crm,
    _envelope_for,
    _redis_client,
    _done_key,
    _seq_key,
    real_contacts,
    redis_client,
    stub_engine_seams,
)
from tests.chatbot.test_engine import _parser_output

# Long enough that a turn which ran unordered would visibly overlap its neighbour, short
# enough that six of them serialised still finish inside the test's own budget.
PARSE_SECONDS = 0.15
STAGGER_SECONDS = 0.05


@pytest.fixture()
def _ordering_on(monkeypatch):
    """S7 mode on at the engine's predicate, not at the settings row.

    Same reason as `test_s7_ordering_and_offload._enable_ordering`: this turn runs on
    `SessionLocal`, the real database, and a singleton left flipped by a test that died
    mid-run would turn S7 mode on for the whole box (AC-810).
    """
    monkeypatch.setattr(engine_mod, "_s7_mode", lambda *args, **kwargs: True)
    monkeypatch.setattr(settings, "chatbot_queue_wait_seconds", 20.0, raising=False)


def test_a_concurrent_poller_batch_and_live_message_keep_order(
    real_contacts, stub_engine_seams, _ordering_on, monkeypatch
) -> None:
    contact = real_contacts("batch-order-coder")
    ingresses = ["poller", "poller", "webhook", "poller", "poller", "poller"]

    # The overlap is measured HERE rather than off the rows, and that is not a shortcut:
    # `chatbot.turns.started_at` is stamped when the row is INSERTED, which is before the
    # ticket wait, so it records when the message ARRIVED and not when its turn began. The
    # parser call is inside the serialised region, so its interval is the turn's execution
    # window, and disjoint intervals are exactly "no two turns for this contact overlap".
    lock = threading.Lock()
    slot_of = threading.local()
    intervals: dict[int, tuple[float, float]] = {}

    # The lane is switched on first, then the parse is replaced by the slow one: S6c is
    # what lets these six turns be ANSWERED rather than refused, and the slow parse is
    # still the serialised region the windows below measure.
    _complete_in_the_crm(monkeypatch)

    def slow_parse(config, user_block):
        start = time.monotonic()
        time.sleep(PARSE_SECONDS)
        end = time.monotonic()
        with lock:
            intervals[slot_of.value] = (start, end)
        return _parser_output(
            message_type="clarification", domain_hint=None, user_goal="checking stock"
        )

    monkeypatch.setattr(parser_mod, "parse", slow_parse)

    results: list[object] = [None] * len(ingresses)
    errors: list[BaseException | None] = [None] * len(ingresses)

    def _fire(slot: int, ingress: str) -> None:
        # The stagger is the whole point: message N leaves 50 ms after message N-1, so
        # arrival order at the CRM is send order, and every one of them is in flight while
        # its predecessor is still being answered.
        time.sleep(slot * STAGGER_SECONDS)
        slot_of.value = slot
        try:
            results[slot] = engine_mod.run_turn(
                _envelope_for(contact, f"ZZT-msg-batch-coder-{slot}", ingress=ingress),
                session_factory=SessionLocal,
            )
        except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
            errors[slot] = exc

    threads = [
        threading.Thread(target=_fire, args=(slot, ingress))
        for slot, ingress in enumerate(ingresses)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [None] * len(ingresses), f"unexpected exception(s): {errors}"
    # `done`, because the lane is switched on and the CRM finishes it. This used to be
    # `failed`, forced by the contract rather than by this test's subject: in S7 mode the
    # CRM owns the tail, so a turn routed to a lane the CRM cannot complete is closed
    # `failed` at `routed` rather than left for a `/complete` that now answers 410
    # (`test_s7_ordering_and_offload.py::TestS7ModeRefusesADelegatingLane` still grades
    # that arm). S6c is what made switching a lane on possible, so the six concurrent
    # turns are now answered end to end - the ordering itself is unaffected either way,
    # because the ticket, the wait and the release all happen before the routing decision.
    assert [getattr(r, "status", None) for r in results] == ["done"] * len(ingresses), [
        getattr(r, "error", None) for r in results
    ]

    # The property per-contact ordering exists for, and the one a sequential test cannot
    # fail: no two turns for this contact were ever running at the same time.
    assert set(intervals) == set(range(len(ingresses))), intervals
    windows = sorted(intervals.items(), key=lambda pair: pair[1][0])
    for (earlier_slot, earlier), (later_slot, later) in zip(windows, windows[1:]):
        assert later[0] >= earlier[1], (
            f"turns {earlier_slot} and {later_slot} for one contact ran at the same time: "
            f"{earlier} overlaps {later}"
        )

    client = _redis_client()
    try:
        assert client.get(_seq_key(contact)) == "6"
        assert client.get(_done_key(contact)) == "6"
    finally:
        client.close()

    db = SessionLocal()
    try:
        rows = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == contact)
            .order_by(ChatbotTurn.created_at)
            .all()
        )
    finally:
        db.close()

    assert len(rows) == len(ingresses)
    by_slot = {int(str(row.message_id).rsplit("-", 1)[1]): row for row in rows}
    assert sorted(by_slot) == list(range(len(ingresses)))
    assert [by_slot[slot].ingress for slot in sorted(by_slot)] == ingresses, (
        "trace rows must carry the ingress each turn actually arrived through, got "
        f"{[by_slot[slot].ingress for slot in sorted(by_slot)]}"
    )

    # The replies came back in the order the turns ran, which is the customer-visible half
    # of the promise: whatever order the CRM took these in, it answered them in that same
    # order and never interleaved them.
    finished_by_run = [by_slot[slot].finished_at for slot, _ in windows]
    assert all(f is not None for f in finished_by_run)
    assert finished_by_run == sorted(finished_by_run), (
        f"the replies finished out of the order the turns ran in: {finished_by_run}"
    )

    # NOT asserted, deliberately: that the run order equals `created_at` order. They are
    # two proxies for one instant taken a few hundred microseconds apart - `created_at` is
    # the dedup read's transaction start, the ticket is the next statement - and under
    # six threads contending for the GIL they can disagree, which was seen here. What
    # orders the turns is the TICKET, and the ticket is not a column, so the assertions
    # above measure the ticket's effects (serialised, in run order) rather than a second
    # proxy for its cause. Closing that gap would mean taking the ticket before the dedup
    # read, and a duplicate would then hold one and release it out of order.
