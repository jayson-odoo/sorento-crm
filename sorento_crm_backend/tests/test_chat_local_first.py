"""Local-first thread reads + delta sync (lane CHAT-LOCAL-FIRST, UAC sections A, B, E).

`documentation/plans/sla/chat-local-first-acceptance-criteria.md`. The contract:

- a contact with stored rows is served from `chat_histories` and the request path makes
  NO Respond call (AC-LF1); the poll schedules at most one background delta read per
  30 s (AC-LF4, AC-DS1);
- an empty thread still gets one live page, then stored (AC-LF2); Respond failing there
  still answers (AC-LF3);
- a delta read upserts by message id and pokes the event bus (AC-DS2); scrolling past
  the oldest stored row makes ONE older read and marks the start when it is short
  (AC-DS3);
- the local row renders media and sender (AC-RF1, AC-RF2), and an existing row is
  filled in from a later read (AC-RF3).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest

from app.models.chat_history import ChatHistory
from app.models.chat_thread_sync_state import ChatThreadSyncState
from app.services import chat_thread_sync_service as sync
from app.services import conversation_event_bus as bus
from app.services import conversation_thread_service as svc
from app.services import respond_rate_limit
from tests._pg_fixture import blank_session

NOW = datetime(2026, 9, 30, 9, 0, 0)
BASE = 1786000000000000

CONTACT = svc.ThreadContact(
    respond_io_id="ZZT551239386",
    phone_number="+60100000011",
    first_name="Zzt",
    last_name="Local",
)


class FakeTransport:
    def __init__(self):
        self.published: list[dict] = []

    def publish(self, channel, payload):
        self.published.append(json.loads(payload))

    def subscribe(self, channel):  # pragma: no cover - not used here
        raise NotImplementedError


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def transport():
    fake = FakeTransport()
    bus.set_transport(fake)
    try:
        yield fake
    finally:
        bus.set_transport(None)


@pytest.fixture
def scheduled():
    """Capture what the request path queues instead of running it on a thread."""
    seen: list = []
    sync.set_runner(seen.append)
    respond_rate_limit.reset()
    try:
        yield seen
    finally:
        sync.set_runner(None)
        respond_rate_limit.reset()


def _mid(i: int) -> int:
    return BASE + i * 1_000_000


def _item(i: int, text: str = "", traffic: str = "incoming", **extra) -> dict:
    item = {
        "messageId": _mid(i),
        "traffic": traffic,
        "message": {"type": "text", "text": text or f"respond body {i}"},
        "sender": {"source": "contact" if traffic == "incoming" else "user", "userId": None},
        "status": [],
    }
    item.update(extra)
    return item


class FakeRespondClient:
    """Newest-first for older walks and the newest page, ascending for newer."""

    api_key = "zzt-key"

    def __init__(self, items: list[dict], *, fail: Exception | None = None):
        self.items = items  # oldest-first
        self.fail = fail
        self.calls: list[dict] = []

    def list_messages(self, identifier, limit=50, cursor=None):
        self.calls.append({"identifier": identifier, "limit": limit, "cursor": cursor})
        if self.fail is not None:
            raise self.fail
        ordered = list(self.items)
        if cursor and str(cursor).startswith("-"):
            anchor = int(str(cursor)[1:])
            return {"items": [i for i in ordered if i["messageId"] > anchor][:limit]}
        if cursor:
            anchor = int(str(cursor))
            return {"items": list(reversed([i for i in ordered if i["messageId"] < anchor]))[:limit]}
        return {"items": list(reversed(ordered))[:limit]}

    def get_message(self, identifier, message_id):
        for i in self.items:
            if str(i["messageId"]) == str(message_id):
                return i
        return {}


def _seed(db, indexes, **cols):
    rows = []
    for i in indexes:
        row = ChatHistory(
            channel="whatsapp",
            contact_id=CONTACT.respond_io_id,
            phone_number=CONTACT.phone_number,
            message=f"local body {i}",
            sent_at=NOW + timedelta(seconds=i),
            type="incoming",
            message_id=str(_mid(i)),
            **cols,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _ids(page):
    return [str(i["messageId"]) for i in page["items"]]


def _stored_ids(db):
    return sorted(
        r.message_id
        for r in db.query(ChatHistory).filter(ChatHistory.contact_id == CONTACT.respond_io_id).all()
    )


def _state(db):
    return (
        db.query(ChatThreadSyncState)
        .filter(ChatThreadSyncState.contact_id == CONTACT.respond_io_id)
        .first()
    )


# ---------------------------------------------------------------------------
# A. Local first
# ---------------------------------------------------------------------------


def test_stored_rows_are_served_locally_with_no_respond_call(db, scheduled):
    """AC-LF1 + AC-DS1: the page is local, Respond is not called on the request path, and
    exactly one delta read is queued for after the response."""
    _seed(db, range(4))
    client = FakeRespondClient([_item(i) for i in range(6)])

    page = svc.fetch_thread_page(db, CONTACT, limit=50, client=client)

    assert page["source"] == "local"
    assert _ids(page) == [str(_mid(i)) for i in range(4)]
    assert client.calls == [], "the request path must not read Respond"
    assert page["sync_scheduled"] is True
    assert scheduled == [CONTACT]


def test_a_poll_inside_the_interval_schedules_nothing(db, scheduled):
    """AC-LF4: the 10 s poll costs zero Respond calls while the last sync is fresh."""
    _seed(db, range(3))
    client = FakeRespondClient([_item(i) for i in range(3)])
    sync.note_first_page(db, CONTACT, oldest_reached=True)  # "synced just now"

    page = svc.fetch_thread_page(db, CONTACT, limit=50, client=client)

    assert page["source"] == "local"
    assert page["sync_scheduled"] is False
    assert scheduled == []
    assert client.calls == []


def test_a_poll_past_the_interval_schedules_one_sync(db, scheduled):
    _seed(db, range(3))
    state = _state(db) or ChatThreadSyncState(channel="whatsapp", contact_id=CONTACT.respond_io_id)
    state.last_synced_at = sync._now() - timedelta(seconds=sync.SYNC_MIN_INTERVAL_SECONDS + 1)
    db.add(state)
    db.flush()

    svc.fetch_thread_page(db, CONTACT, limit=50, client=FakeRespondClient([]))
    svc.fetch_thread_page(db, CONTACT, limit=50, client=FakeRespondClient([]))

    # The runner seam runs inline and releases, so the second call sees the interval
    # rule (the state row still says "synced 31 s ago" because the runner did not sync).
    assert scheduled == [CONTACT, CONTACT]


def test_a_scroll_back_or_jump_never_schedules_a_sync(db, scheduled):
    _seed(db, range(6))
    client = FakeRespondClient([_item(i) for i in range(6)])
    sync.note_first_page(db, CONTACT, oldest_reached=True)

    svc.fetch_thread_page(db, CONTACT, around=str(_mid(3)), limit=3, client=client)
    svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=3, client=client)

    assert scheduled == []
    assert client.calls == []


def test_an_empty_thread_reads_one_live_page_and_stores_it(db, scheduled):
    """AC-LF2: first open of a never-ingested contact is today's live read, then stored,
    and that read counts as the first sync."""
    client = FakeRespondClient([_item(i) for i in range(4)])

    page = svc.fetch_thread_page(db, CONTACT, limit=50, client=client)

    assert page["source"] == "respond"
    assert len(client.calls) == 1
    assert page["backfilled"] == 4
    assert _stored_ids(db) == [str(_mid(i)) for i in range(4)]
    state = _state(db)
    assert state is not None and state.last_synced_at is not None
    assert state.oldest_reached is True, "a short newest page IS the whole thread"
    assert scheduled == [], "the live page is the sync; nothing more is queued"


def test_a_second_open_after_the_live_page_is_local(db, scheduled):
    client = FakeRespondClient([_item(i) for i in range(4)])
    svc.fetch_thread_page(db, CONTACT, limit=50, client=client)

    page = svc.fetch_thread_page(db, CONTACT, limit=50, client=client)

    assert page["source"] == "local"
    assert len(client.calls) == 1
    assert _ids(page) == [str(_mid(i)) for i in range(4)]


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("respond is down"),
        httpx.ReadTimeout("timed out"),
        httpx.HTTPStatusError(
            "500",
            request=httpx.Request("GET", "https://api.respond.io/x"),
            response=httpx.Response(500),
        ),
    ],
)
def test_respond_failing_on_an_empty_thread_still_answers(db, scheduled, failure):
    """AC-LF3: a timeout, a 5xx or any error on the live fallback is a local (empty)
    page, never a 500."""
    page = svc.fetch_thread_page(db, CONTACT, limit=50, client=FakeRespondClient([], fail=failure))
    assert page["source"] == "local"
    assert page["items"] == []
    assert page["error"] is None


def test_respond_failing_with_stored_rows_is_invisible(db, scheduled):
    _seed(db, range(3))
    page = svc.fetch_thread_page(
        db, CONTACT, limit=50, client=FakeRespondClient([], fail=RuntimeError("down"))
    )
    assert page["source"] == "local"
    assert _ids(page) == [str(_mid(i)) for i in range(3)]


# ---------------------------------------------------------------------------
# B. Delta sync
# ---------------------------------------------------------------------------


def test_sync_newer_reads_once_past_the_newest_stored_row_and_pokes(db, transport):
    """AC-DS1 / AC-DS2 / AC-DS4."""
    _seed(db, range(4))
    client = FakeRespondClient([_item(i) for i in range(6)])

    result = sync.sync_newer(db, CONTACT, client)

    assert client.calls == [{"identifier": CONTACT.respond_io_id, "limit": 50, "cursor": f"-{_mid(3)}"}]
    assert result["fetched"] == 2 and result["written"] == 2 and result["error"] is None
    assert _stored_ids(db) == [str(_mid(i)) for i in range(6)]
    assert [e["type"] for e in transport.published] == ["message"]
    assert transport.published[0]["contact_id"] == CONTACT.respond_io_id
    state = _state(db)
    assert state.last_synced_at is not None and state.last_error is None


def test_sync_newer_with_nothing_new_writes_nothing_and_pokes_nobody(db, transport):
    _seed(db, range(4))
    client = FakeRespondClient([_item(i) for i in range(4)])

    result = sync.sync_newer(db, CONTACT, client)

    assert result["written"] == 0
    assert transport.published == []
    assert _state(db).last_synced_at is not None


def test_sync_newer_records_a_failure_and_never_raises(db, transport):
    _seed(db, range(2))
    client = FakeRespondClient([], fail=RuntimeError("respond is down"))

    result = sync.sync_newer(db, CONTACT, client)

    assert result["error"] == "respond is down"
    assert "respond is down" in _state(db).last_error
    assert transport.published == []


def test_sync_newer_under_a_429_backoff_is_skipped_not_sent(db, transport):
    respond_rate_limit.reset()
    _seed(db, range(2))
    limited = httpx.HTTPStatusError(
        "429",
        request=httpx.Request("GET", "https://api.respond.io/x"),
        response=httpx.Response(429, headers={"Retry-After": "30"}),
    )
    client = FakeRespondClient([], fail=limited)

    first = sync.sync_newer(db, CONTACT, client)
    client.fail = None
    second = sync.sync_newer(db, CONTACT, client)

    assert first["rate_limited"] is True
    assert second["rate_limited"] is True, "inside Retry-After nothing is sent"
    assert len(client.calls) == 1
    respond_rate_limit.reset()


def test_claim_is_taken_once_per_interval(db):
    _seed(db, range(1))
    assert sync._claim_sync(db, CONTACT) is True
    assert sync._claim_sync(db, CONTACT) is False, "a second process inside the window loses"
    later = sync._now() + timedelta(seconds=sync.SYNC_MIN_INTERVAL_SECONDS + 1)
    assert sync._claim_sync(db, CONTACT, now=later) is True


def test_scroll_back_past_the_oldest_stored_row_reads_one_older_page(db, scheduled):
    """AC-DS3: local holds m3..m5, Respond holds m0..m5. Paging before m3 pulls the older
    rows in ONE call; a short page marks the start, so paging further is local only."""
    _seed(db, [3, 4, 5])
    client = FakeRespondClient([_item(i) for i in range(6)])

    page = svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)

    assert client.calls == [{"identifier": CONTACT.respond_io_id, "limit": 50, "cursor": str(_mid(3))}]
    assert _ids(page) == [str(_mid(1)), str(_mid(2))]
    assert page["source"] == "local"
    assert _stored_ids(db) == [str(_mid(i)) for i in range(6)]
    assert _state(db).oldest_reached is True

    older = svc.fetch_thread_page(db, CONTACT, before=str(_mid(1)), limit=2, client=client)
    assert _ids(older) == [str(_mid(0))]
    assert older["has_more_older"] is False
    assert len(client.calls) == 1, "the start was reached; Respond is not asked again"


def test_scroll_back_with_enough_stored_rows_reads_nothing(db, scheduled):
    _seed(db, range(6))
    client = FakeRespondClient([_item(i) for i in range(6)])

    page = svc.fetch_thread_page(db, CONTACT, before=str(_mid(4)), limit=2, client=client)

    assert _ids(page) == [str(_mid(2)), str(_mid(3))]
    assert client.calls == []


def test_scroll_back_when_respond_fails_answers_what_is_stored(db, scheduled):
    _seed(db, [3, 4, 5])
    client = FakeRespondClient([], fail=RuntimeError("down"))

    page = svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)

    assert page["items"] == []
    assert page["source"] == "local"
    assert _state(db).oldest_reached is False


def test_scroll_back_after_a_failed_older_read_waits_out_the_interval(db, scheduled):
    """Security review finding 4: a contact whose key 404s on Respond must not cost one
    live call per scroll-back. The next attempt waits SYNC_MIN_INTERVAL_SECONDS."""
    _seed(db, [3, 4, 5])
    # Committed: the failed read rolls the session back, which under the blank session
    # would discard a merely flushed seed (in production nothing else is pending there).
    db.commit()
    client = FakeRespondClient([], fail=RuntimeError("404 not found"))

    svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)
    svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)
    svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)

    assert len(client.calls) == 1
    state = _state(db)
    state.last_error_at = sync._now() - timedelta(seconds=sync.SYNC_MIN_INTERVAL_SECONDS + 1)
    db.flush()
    svc.fetch_thread_page(db, CONTACT, before=str(_mid(3)), limit=2, client=client)
    assert len(client.calls) == 2


def test_sync_older_on_a_full_page_keeps_asking_next_time(db):
    _seed(db, [60])
    client = FakeRespondClient([_item(i) for i in range(61)])

    result = sync.sync_older(db, CONTACT, client)

    assert result["fetched"] == 50 and result["oldest_reached"] is False
    assert _state(db).oldest_reached is False


# ---------------------------------------------------------------------------
# E. Local row fidelity
# ---------------------------------------------------------------------------


def test_a_media_row_renders_an_attachment_block(db):
    """AC-RF1: the stored placeholder is not shown as a caption; a real caption is."""
    (placeholder,) = _seed(
        db, [1], media_url="https://cdn/x.jpg", media_type="image", media_file_name="x.jpg"
    )
    placeholder.message = "[image] x.jpg"
    (captioned,) = _seed(
        db, [2], media_url="https://cdn/y.pdf", media_type="file", media_file_name="quote.pdf"
    )
    captioned.message = "here is the quote"
    db.flush()

    items = {str(i["messageId"]): i for i in svc.fetch_thread_page(db, CONTACT, limit=10)["items"]}
    first = items[str(_mid(1))]["message"]
    assert first["type"] == "attachment"
    assert first["attachment"] == {"type": "image", "url": "https://cdn/x.jpg", "fileName": "x.jpg"}
    assert "text" not in first
    second = items[str(_mid(2))]["message"]
    assert second["attachment"]["url"] == "https://cdn/y.pdf"
    assert second["text"] == "here is the quote"


def test_sender_source_comes_from_the_column_when_stored(db):
    """AC-RF2."""
    _seed(db, [1])
    (bot,) = _seed(db, [2], sender_source="bot")
    bot.type = "outgoing"
    (user,) = _seed(db, [3], sender_source="user", sender_user_id="7781")
    user.type = "outgoing"
    db.flush()

    items = {str(i["messageId"]): i for i in svc.fetch_thread_page(db, CONTACT, limit=10)["items"]}
    assert items[str(_mid(1))]["sender"] == {"source": "contact"}
    assert items[str(_mid(2))]["sender"] == {"source": "bot"}
    assert items[str(_mid(3))]["sender"] == {"source": "user", "userId": "7781"}


def test_a_respond_read_stores_media_and_sender(db):
    item = _item(
        1,
        traffic="outgoing",
        message={
            "type": "attachment",
            "attachment": {"type": "file", "url": "https://cdn/PO.xlsx", "fileName": "PO%20SPO.xlsx"},
        },
        sender={"source": "user", "userId": 4411},
    )
    svc.persist_messages(db, CONTACT, [item])

    row = db.query(ChatHistory).filter(ChatHistory.message_id == str(_mid(1))).one()
    assert (row.media_url, row.media_type, row.media_file_name) == (
        "https://cdn/PO.xlsx", "file", "PO SPO.xlsx",
    )
    assert (row.sender_source, row.sender_user_id) == ("user", "4411")
    assert row.message == "[file] PO SPO.xlsx"


def test_an_existing_row_is_filled_in_from_a_later_read(db):
    """AC-RF3: the ONLY backfill for pre-lane rows. Fill-if-null: the text stands."""
    (row,) = _seed(db, [1])
    row.message = "[image] x.jpg"
    db.flush()
    item = _item(
        1,
        message={"type": "attachment", "attachment": {"type": "image", "url": "https://cdn/x.jpg", "fileName": "x.jpg"}},
        sender={"source": "contact"},
    )

    written = svc.persist_messages(db, CONTACT, [item])
    db.flush()
    db.expire_all()

    assert written == 0
    row = db.query(ChatHistory).filter(ChatHistory.message_id == str(_mid(1))).one()
    assert row.media_url == "https://cdn/x.jpg"
    assert row.media_type == "image"
    assert row.sender_source == "contact"
    assert row.message == "[image] x.jpg"


def test_a_stored_row_keeps_its_activity_stamp_for_the_reconcile(db):
    svc.persist_messages(db, CONTACT, [_item(1), _item(2)])
    state = _state(db)
    assert state is not None
    assert state.last_activity_at == datetime.utcfromtimestamp(_mid(2) / 1_000_000)
