"""Respond-side timestamp resolver.

Covers UAC OBS-S4-19 .. OBS-S4-25, reworked by lane CHAT-DELIVERY-RESOLVER (29 Oct 2026):
the real v2 `status[]` list, a backoff on 404, and a stored reason.

Resolves `respond_ts` / `delivery_status` for chat rows by calling
`GET /v2/contact/{id}/message/{messageId}`. Chosen over polling Respond's message
list: the lookup is targeted, and a 404 is itself the signal that a message we
believed we sent never existed.
"""
from datetime import datetime, timedelta

import httpx
import pytest

from app.models.chat_history import ChatHistory
from app.services import chat_message_resolver as svc
from tests._pg_fixture import blank_session


# No column-type shims needed: on the real schema JSONB/ARRAY are native and the
# BigInteger primary key is backed by a sequence, so inserts fill it themselves.
@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# Recorded respond.io v2 shapes (CHAT-DELIVERY-RESOLVER, crew evidence 29 Oct 2026, ids masked).
# `GET /v2/contact/{id}/message/{messageId}` answers with `status` as a LIST of
# `{value, timestamp(ms)}` entries - never a top-level `timestamp` - the same shape
# tests/test_respond_window_state.py and tests/test_respond_webhook_ingest.py record.

# A normal bot reply: pending 22:14:46 MYT -> delivered + read 22:14:48.
NORMAL_ID = "1793283285990000"
NORMAL_SENT_AT = datetime(2026, 10, 29, 14, 14, 45, 990000)
NORMAL_REPLY = {
    "messageId": int(NORMAL_ID),
    "traffic": "outgoing",
    "message": {"type": "text", "text": "masked"},
    "status": [
        {"value": "pending", "timestamp": 1793283286205},
        {"value": "delivered", "timestamp": 1793283288118},
        {"value": "read", "timestamp": 1793283288530},
    ],
}

# Tonight's lagging reply: id issued 22:17:30 MYT, respond.io answered 404 until it
# dispatched at 22:44 (pending 22:44:06 -> sent 22:44:10 -> delivered 22:44:11).
LAGGED_ID = "1793283450000000"
LAGGED_SENT_AT = datetime(2026, 10, 29, 14, 17, 30)
LAGGED_DISPATCHED = {
    "messageId": int(LAGGED_ID),
    "traffic": "outgoing",
    "message": {"type": "text", "text": "masked"},
    "status": [
        {"value": "pending", "timestamp": 1793285046412},
        {"value": "sent", "timestamp": 1793285050877},
        {"value": "delivered", "timestamp": 1793285051903},
    ],
}


def _not_found(text='{"message": "Message not found"}'):
    """What RespondClient.get_message raises: httpx's raise_for_status on a 404."""
    request = httpx.Request("GET", "https://api.respond.io/v2/contact/id:1/message/1")
    response = httpx.Response(404, text=text, request=request)
    return httpx.HTTPStatusError("404 Not Found", request=request, response=response)


class FakeClient:
    """Stands in for RespondClient. Records calls so we can assert what was asked."""

    def __init__(self, responses=None, raises=None):
        self.responses = responses or {}
        self.raises = raises or {}
        self.calls = []

    def get_message(self, identifier, message_id):
        self.calls.append((str(identifier), str(message_id)))
        key = str(message_id)
        if key in self.raises:
            raise self.raises[key]
        return self.responses.get(key, {})


def _row(
    db,
    *,
    message_id=LAGGED_ID,
    sent_at=LAGGED_SENT_AT,
    respond_ts="derive",
    attempts=0,
    type="outgoing",
    contact_id="900000063",
    delivery_status=None,
):
    if respond_ts == "derive":
        respond_ts = svc.respond_ts_from_message_id(message_id, sent_at=sent_at)
    row = ChatHistory(
        channel="whatsapp",
        contact_id=contact_id,
        phone_number="+60160000517",
        message="hi",
        sent_at=sent_at,
        type=type,
        message_id=message_id,
        respond_ts=respond_ts,
        resolve_attempts=attempts,
        delivery_status=delivery_status,
    )
    db.add(row)
    db.commit()
    return row


def _at(minutes):
    return LAGGED_SENT_AT + timedelta(minutes=minutes)


# --- 1. the real v2 response lands in delivery_status --------------------------------


def test_normal_reply_resolves_to_read_with_receipt_times_and_trace(db):
    row = _row(db, message_id=NORMAL_ID, sent_at=NORMAL_SENT_AT)
    client = FakeClient({NORMAL_ID: NORMAL_REPLY})

    out = svc.resolve_pending(db, client=client, limit=10, now=NORMAL_SENT_AT + timedelta(minutes=2))

    db.refresh(row)
    assert out["resolved"] == 1
    assert row.delivery_status == "read"
    assert row.delivered_ts == datetime(2026, 10, 29, 14, 14, 48, 118000)
    assert row.read_ts == datetime(2026, 10, 29, 14, 14, 48, 530000)
    # The timeline is stored as respond.io gave it.
    assert row.delivery_trace == NORMAL_REPLY["status"]
    assert row.delivery_error is None
    # respond_ts stays the message-id clock already derived at ingest.
    assert row.respond_ts == datetime(2026, 10, 29, 14, 14, 45, 990000)


def test_respond_ts_filled_from_earliest_status_when_missing(db):
    row = _row(db, message_id=NORMAL_ID, sent_at=NORMAL_SENT_AT, respond_ts=None)
    client = FakeClient({NORMAL_ID: NORMAL_REPLY})
    svc.resolve_pending(db, client=client, limit=10, now=NORMAL_SENT_AT + timedelta(minutes=2))
    db.refresh(row)
    assert row.respond_ts == datetime(2026, 10, 29, 14, 14, 46, 205000)


def test_sent_and_delivered_are_not_terminal_and_progress_to_read(db):
    row = _row(db)
    client = FakeClient({LAGGED_ID: {**LAGGED_DISPATCHED, "status": LAGGED_DISPATCHED["status"][:2]}})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    db.refresh(row)
    assert row.delivery_status == "sent"

    client.responses[LAGGED_ID] = LAGGED_DISPATCHED
    svc.resolve_pending(db, client=client, limit=10, now=_at(2))
    db.refresh(row)
    assert row.delivery_status == "delivered"
    assert row.delivered_ts == datetime(2026, 10, 29, 14, 44, 11, 903000)


def test_pending_only_is_stored_as_pending_and_polled_again(db):
    row = _row(db)
    client = FakeClient({LAGGED_ID: {**LAGGED_DISPATCHED, "status": LAGGED_DISPATCHED["status"][:1]}})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    db.refresh(row)
    assert row.delivery_status == "pending"
    svc.resolve_pending(db, client=client, limit=10, now=_at(2))
    assert len(client.calls) == 2


def test_read_rows_are_not_polled_again(db):
    _row(db, delivery_status="read")
    client = FakeClient()
    svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    assert client.calls == []


def test_passes_contact_identifier_not_just_message_id(db):
    """GET /v2/contact/{identifier}/message/{id} needs both."""
    _row(db, contact_id="999")
    client = FakeClient({LAGGED_ID: LAGGED_DISPATCHED})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    assert client.calls == [("999", LAGGED_ID)]


def test_skips_rows_without_message_id(db):
    _row(db, message_id=None, respond_ts=None)
    client = FakeClient()
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(5))
    assert client.calls == []
    assert out["resolved"] == 0


def test_respects_limit(db):
    for i in range(5):
        _row(db, message_id=f"m{i}", respond_ts=None)
    client = FakeClient()
    svc.resolve_pending(db, client=client, limit=2, now=_at(5))
    assert len(client.calls) == 2


# --- incoming rows: only the clock is ever missing -------------------------------------


def test_incoming_row_with_respond_ts_is_not_polled(db):
    """Incoming messages carry `status: []`; delivery is not ours to resolve."""
    _row(db, type="incoming")
    client = FakeClient()
    svc.resolve_pending(db, client=client, limit=10, now=_at(5))
    assert client.calls == []


def test_incoming_row_without_respond_ts_takes_the_message_id_clock(db):
    row = _row(db, type="incoming", respond_ts=None)
    client = FakeClient({LAGGED_ID: {"messageId": int(LAGGED_ID), "traffic": "incoming", "status": []}})
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(5))
    db.refresh(row)
    assert out["resolved"] == 1
    assert row.respond_ts == LAGGED_SENT_AT
    assert row.delivery_status is None


def test_incoming_resolved_row_drops_out_of_the_queue(db):
    _row(db, type="incoming", respond_ts=None)
    client = FakeClient({LAGGED_ID: {"messageId": int(LAGGED_ID), "traffic": "incoming", "status": []}})
    svc.resolve_pending(db, client=client, limit=10, now=_at(5))
    svc.resolve_pending(db, client=client, limit=10, now=_at(500))
    assert len(client.calls) == 1


# --- 2. a 404 shortly after the send is "not dispatched yet" ---------------------------


def test_404_inside_the_first_hour_never_writes_not_sent(db):
    """Tonight: 404 at every tick until respond.io dispatched ~25 min later."""
    row = _row(db)
    client = FakeClient(raises={LAGGED_ID: _not_found()})

    for minute in (1, 2, 5, 15, 30):
        svc.resolve_pending(db, client=client, limit=10, now=_at(minute))
        db.refresh(row)
        assert row.delivery_status is None, minute

    assert len(client.calls) == 5
    assert row.resolve_attempts == 5
    assert row.delivery_error == "HTTP 404: Message not found"


def test_backoff_skips_rows_that_are_not_due(db):
    row = _row(db)
    client = FakeClient(raises={LAGGED_ID: _not_found()})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    # Next attempt is due 2 min after the send, not on the next 60 s tick.
    svc.resolve_pending(db, client=client, limit=10, now=_at(1.5))
    assert len(client.calls) == 1
    svc.resolve_pending(db, client=client, limit=10, now=_at(2))
    assert len(client.calls) == 2
    db.refresh(row)
    assert row.resolve_attempts == 2


def test_not_due_rows_do_not_starve_the_batch(db):
    """A batch limit must be spent on due rows, not on rows still backing off."""
    for i in range(3):
        _row(db, message_id=f"early{i}", respond_ts=None, attempts=1, sent_at=_at(59))
    due = _row(db, message_id="due", respond_ts=None)
    client = FakeClient(raises={"due": _not_found()})
    svc.resolve_pending(db, client=client, limit=1, now=_at(60))
    assert client.calls == [("900000063", "due")]
    db.refresh(due)
    assert due.resolve_attempts > 0


def test_a_late_tick_skips_ahead_instead_of_firing_every_minute(db):
    """A row first seen 3 h after its send (scheduler down) jumps to the 4 h slot."""
    row = _row(db)
    client = FakeClient(raises={LAGGED_ID: _not_found()})
    svc.resolve_pending(db, client=client, limit=10, now=_at(180))
    svc.resolve_pending(db, client=client, limit=10, now=_at(181))
    assert len(client.calls) == 1
    db.refresh(row)
    assert row.resolve_attempts == sum(1 for m in svc.RESOLVE_SCHEDULE_MINUTES if m <= 180)


def test_404_after_an_hour_writes_not_sent_with_the_reason(db):
    row = _row(db, attempts=5)
    client = FakeClient(raises={LAGGED_ID: _not_found()})
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    db.refresh(row)
    assert out["not_sent"] == 1
    assert row.delivery_status == "not_sent"
    assert row.delivery_error == "HTTP 404: Message not found"


def test_404_reason_falls_back_to_the_raw_body(db):
    row = _row(db, attempts=5)
    client = FakeClient(raises={LAGGED_ID: _not_found(text="no such message")})
    svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    db.refresh(row)
    assert row.delivery_error == "HTTP 404: no such message"


def test_not_sent_is_upgraded_by_a_later_200(db):
    """The owner's case: provisional not_sent, then respond.io dispatched it."""
    row = _row(db, attempts=5)
    client = FakeClient(raises={LAGGED_ID: _not_found()})
    svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    db.refresh(row)
    assert row.delivery_status == "not_sent"

    client.raises.clear()
    client.responses[LAGGED_ID] = LAGGED_DISPATCHED
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(240))
    db.refresh(row)
    assert out["resolved"] == 1
    assert row.delivery_status == "delivered"
    assert row.delivery_error is None
    assert row.delivery_trace == LAGGED_DISPATCHED["status"]


def test_rows_already_marked_not_sent_by_the_old_resolver_are_rechecked(db):
    """Prod rows the 5 x 404 rule closed tonight reopen at the next slot."""
    _row(db, attempts=5, delivery_status="not_sent")
    client = FakeClient({LAGGED_ID: LAGGED_DISPATCHED})
    svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    assert client.calls == [("900000063", LAGGED_ID)]


def test_404_on_the_last_attempt_is_final(db):
    row = _row(db, attempts=svc.MAX_RESOLVE_ATTEMPTS - 1)
    client = FakeClient(raises={LAGGED_ID: _not_found()})
    svc.resolve_pending(db, client=client, limit=10, now=_at(24 * 60))
    db.refresh(row)
    assert row.resolve_attempts == svc.MAX_RESOLVE_ATTEMPTS
    assert row.delivery_status == "not_sent"
    svc.resolve_pending(db, client=client, limit=10, now=_at(30 * 60))
    assert len(client.calls) == 1


def test_schedule_waits_at_least_an_hour_and_ends_within_the_lookback():
    assert svc.RESOLVE_SCHEDULE_MINUTES == sorted(svc.RESOLVE_SCHEDULE_MINUTES)
    assert svc.NOT_SENT_AFTER_MINUTES >= 60
    assert svc.RESOLVE_SCHEDULE_MINUTES[-1] < svc.RESOLVE_LOOKBACK.total_seconds() / 60
    assert svc.MAX_RESOLVE_ATTEMPTS == len(svc.RESOLVE_SCHEDULE_MINUTES)


def test_rows_older_than_the_lookback_are_not_backfilled(db):
    """No silent backfill of the historic NULL rows: that is the owner's call."""
    _row(db, attempts=5)
    client = FakeClient({LAGGED_ID: LAGGED_DISPATCHED})
    svc.resolve_pending(db, client=client, limit=10, now=LAGGED_SENT_AT + svc.RESOLVE_LOOKBACK + timedelta(minutes=1))
    assert client.calls == []


# --- 3. a real respond.io delivery failure ---------------------------------------------


def test_failed_status_maps_to_failed_with_the_reason_and_is_terminal(db):
    row = _row(db)
    failed = {
        **LAGGED_DISPATCHED,
        "status": [
            {"value": "pending", "timestamp": 1793285046412},
            {"value": "failed", "timestamp": 1793285050877, "message": "Message undeliverable"},
        ],
    }
    client = FakeClient({LAGGED_ID: failed})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    db.refresh(row)
    assert row.delivery_status == "failed"
    assert row.delivery_error == "Message undeliverable"
    assert row.delivery_trace == failed["status"]

    svc.resolve_pending(db, client=client, limit=10, now=_at(60))
    assert len(client.calls) == 1


def test_failed_without_text_still_carries_a_reason(db):
    row = _row(db)
    client = FakeClient({LAGGED_ID: {"status": [{"value": "failed", "timestamp": 1793285050877}]}})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    db.refresh(row)
    assert row.delivery_status == "failed"
    assert row.delivery_error == "respond.io status failed"


# --- transient errors ------------------------------------------------------------------


def test_transient_error_never_concludes_not_sent(db):
    """A 500 must not be read as 'never sent', even past the hour."""
    row = _row(db, attempts=5)
    request = httpx.Request("GET", "https://api.respond.io/x")
    err = httpx.HTTPStatusError("503", request=request, response=httpx.Response(503, request=request))
    client = FakeClient(raises={LAGGED_ID: err})

    out = svc.resolve_pending(db, client=client, limit=10, now=_at(60))

    db.refresh(row)
    assert out["failed"] == 1
    assert row.delivery_status is None
    assert row.resolve_attempts == 6


def test_one_bad_row_does_not_abort_the_batch(db):
    _row(db, message_id="bad", respond_ts=None)
    good = _row(db)
    client = FakeClient({LAGGED_ID: LAGGED_DISPATCHED}, raises={"bad": RuntimeError("boom")})

    out = svc.resolve_pending(db, client=client, limit=10, now=_at(1))

    db.refresh(good)
    assert good.delivery_status == "delivered"
    assert out["resolved"] == 1 and out["failed"] == 1


def test_response_without_status_or_clock_is_not_resolved(db):
    # A non-timestamp id, so the message id cannot supply the clock either.
    row = _row(db, message_id="m1", respond_ts=None)
    client = FakeClient({"m1": {}})
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    db.refresh(row)
    assert out["resolved"] == 0
    assert row.respond_ts is None
    assert row.delivery_status is None
    assert row.resolve_attempts == 1

# --- respond_ts derived from the Respond message id -------------------------
#
# Respond's `messageId` IS the message's epoch-microsecond timestamp, so the
# authoritative clock is already in the ingest payload and needs no HTTP call.
# Covers UAC OBS-S4-26 .. OBS-S4-31.

SENT_AT = datetime(2026, 7, 21, 2, 48, 45, 363000)


def test_microsecond_message_id_yields_respond_ts():
    assert svc.respond_ts_from_message_id(
        "1784602125363985", sent_at=SENT_AT
    ) == datetime(2026, 7, 21, 2, 48, 45, 363985)


def test_whole_second_incoming_message_id_yields_respond_ts():
    """Inbound WhatsApp ids land on exact seconds - that granularity is real."""
    assert svc.respond_ts_from_message_id(
        "1784602116000000", sent_at=datetime(2026, 7, 21, 2, 48, 36)
    ) == datetime(2026, 7, 21, 2, 48, 36)


def test_millisecond_epoch_is_rejected_not_read_as_microseconds():
    """1784602125363 as microseconds is 1970 - implausible, so refuse it."""
    assert svc.respond_ts_from_message_id("1784602125363", sent_at=SENT_AT) is None


def test_non_timestamp_id_is_rejected():
    """A short numeric id divided by 1e6 lands in 1970, nowhere near sent_at."""
    assert svc.respond_ts_from_message_id("1234556", sent_at=SENT_AT) is None


def test_non_numeric_and_absent_ids_are_rejected():
    assert svc.respond_ts_from_message_id("abc", sent_at=SENT_AT) is None
    assert svc.respond_ts_from_message_id(None, sent_at=SENT_AT) is None
    assert svc.respond_ts_from_message_id("", sent_at=SENT_AT) is None


def test_id_far_from_sent_at_is_rejected():
    """Guard against ids that parse but describe a different message entirely."""
    assert svc.respond_ts_from_message_id(
        "1784602125363985", sent_at=datetime(2020, 1, 1)
    ) is None


def test_a_404_after_a_confirmed_delivery_keeps_the_receipt(db):
    """A later 404 (rotated workspace key, say) must not erase a real delivery."""
    row = _row(db)
    client = FakeClient({LAGGED_ID: LAGGED_DISPATCHED})
    svc.resolve_pending(db, client=client, limit=10, now=_at(1))

    client.responses.clear()
    client.raises[LAGGED_ID] = _not_found()
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(240))

    db.refresh(row)
    assert len(client.calls) == 2
    assert out["not_sent"] == 0
    assert row.delivery_status == "delivered"
    assert row.delivery_error is None


def test_empty_response_on_a_row_with_its_clock_is_not_counted_resolved(db):
    _row(db)
    client = FakeClient({LAGGED_ID: {"status": []}})
    out = svc.resolve_pending(db, client=client, limit=10, now=_at(1))
    assert out["resolved"] == 0
