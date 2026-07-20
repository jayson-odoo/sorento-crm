"""Chat history admin listing: filters, keyset pagination, thread view.

Covers UAC OBS-S5-01 .. OBS-S5-12.

`chat_histories` is high-volume and its `contact_id` is the **Respond.io id string**,
not `respond_contacts.id` — so name resolution is a join, and the UI must never surface
the raw id (no opaque identifiers in the UI). Pagination is keyset on
`(sent_at, id)` because OFFSET degrades badly once the table is large.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.database import Base
from app.models.chat_history import ChatHistory
from app.services import chat_history_query as svc


def _prep(*models):
    for model in models:
        for col in model.__table__.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
                col.server_default = None
            if col.primary_key and isinstance(col.type, BigInteger):
                col.type = Integer()


@pytest.fixture
def db():
    _prep(ChatHistory)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[ChatHistory.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


NOW = datetime(2026, 7, 20, 12, 0, 0)


def _msg(
    db,
    *,
    sent_at,
    type="incoming",
    contact_id="445239409",
    phone="+60165622487",
    message="hello",
    turn_id=None,
    respond_ts=None,
    first_name=None,
    last_name=None,
):
    row = ChatHistory(
        channel="whatsapp",
        contact_id=contact_id,
        phone_number=phone,
        message=message,
        sent_at=sent_at,
        type=type,
        turn_id=turn_id,
        respond_ts=respond_ts,
        first_name=first_name,
        last_name=last_name,
    )
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------------- #
# Filters                                                                     #
# --------------------------------------------------------------------------- #
def test_date_range_filters_on_sent_at(db):
    _msg(db, sent_at=NOW - timedelta(days=3), message="old")
    _msg(db, sent_at=NOW - timedelta(hours=2), message="recent")
    rows, _ = svc.list_messages(db, date_from=NOW - timedelta(days=1), date_to=NOW)
    assert [r.message for r in rows] == ["recent"]


def test_default_window_is_last_24h(db):
    _msg(db, sent_at=NOW - timedelta(days=3), message="old")
    _msg(db, sent_at=NOW - timedelta(hours=2), message="recent")
    rows, _ = svc.list_messages(db, now=NOW)
    assert [r.message for r in rows] == ["recent"]


def test_contact_filter(db):
    _msg(db, sent_at=NOW, contact_id="111", message="a")
    _msg(db, sent_at=NOW, contact_id="222", message="b")
    rows, _ = svc.list_messages(db, contact_id="222", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["b"]


def test_direction_filter(db):
    _msg(db, sent_at=NOW, type="incoming", message="in")
    _msg(db, sent_at=NOW, type="outgoing", message="out")
    rows, _ = svc.list_messages(db, direction="outgoing", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["out"]


def test_search_matches_message_text(db):
    _msg(db, sent_at=NOW, message="SRTKS2405 stock level")
    _msg(db, sent_at=NOW, message="how to submit complaint")
    rows, _ = svc.list_messages(db, search="srtks", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert len(rows) == 1


def test_search_matches_phone(db):
    _msg(db, sent_at=NOW, phone="+60111111111", message="a")
    _msg(db, sent_at=NOW, phone="+60222222222", message="b")
    rows, _ = svc.list_messages(db, search="222222", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["b"]


# --------------------------------------------------------------------------- #
# Ordering + keyset pagination                                                #
# --------------------------------------------------------------------------- #
def test_newest_first(db):
    _msg(db, sent_at=NOW - timedelta(minutes=5), message="older")
    _msg(db, sent_at=NOW - timedelta(minutes=1), message="newer")
    rows, _ = svc.list_messages(db, now=NOW)
    assert [r.message for r in rows] == ["newer", "older"]


def test_keyset_pagination_walks_without_gaps_or_repeats(db):
    for i in range(10):
        _msg(db, sent_at=NOW - timedelta(minutes=i), message=f"m{i}")

    seen = []
    cursor = None
    for _ in range(5):
        rows, next_cursor = svc.list_messages(db, now=NOW, limit=3, cursor=cursor)
        seen.extend(r.message for r in rows)
        if not next_cursor:
            break
        cursor = next_cursor

    assert seen == [f"m{i}" for i in range(10)]
    assert len(seen) == len(set(seen))


def test_ties_on_sent_at_are_broken_by_id(db):
    """Identical timestamps must still paginate deterministically."""
    same = NOW - timedelta(minutes=1)
    for i in range(5):
        _msg(db, sent_at=same, message=f"t{i}")

    seen = []
    cursor = None
    while True:
        rows, cursor = svc.list_messages(db, now=NOW, limit=2, cursor=cursor)
        seen.extend(r.message for r in rows)
        if not cursor:
            break
    assert sorted(seen) == [f"t{i}" for i in range(5)]
    assert len(seen) == 5


def test_cursor_none_when_exhausted(db):
    _msg(db, sent_at=NOW, message="only")
    _, cursor = svc.list_messages(db, now=NOW, limit=10)
    assert cursor is None


# --------------------------------------------------------------------------- #
# Thread view                                                                 #
# --------------------------------------------------------------------------- #
def test_thread_returns_messages_around_an_anchor(db):
    for i in range(10):
        _msg(db, sent_at=NOW - timedelta(minutes=i), contact_id="777", message=f"m{i}")
    anchor = _msg(db, sent_at=NOW - timedelta(minutes=4, seconds=30), contact_id="777", message="anchor")

    rows = svc.get_thread(db, contact_id="777", anchor_id=anchor.id, before=2, after=2)
    messages = [r.message for r in rows]
    assert "anchor" in messages
    assert len(messages) <= 5


def test_thread_is_scoped_to_one_contact(db):
    a = _msg(db, sent_at=NOW, contact_id="111", message="mine")
    _msg(db, sent_at=NOW, contact_id="222", message="theirs")
    rows = svc.get_thread(db, contact_id="111", anchor_id=a.id)
    assert [r.message for r in rows] == ["mine"]


def test_thread_ordered_oldest_first(db):
    """A transcript reads top-down; the grid reads newest-first. Different orders."""
    _msg(db, sent_at=NOW - timedelta(minutes=2), contact_id="9", message="first")
    anchor = _msg(db, sent_at=NOW - timedelta(minutes=1), contact_id="9", message="second")
    _msg(db, sent_at=NOW, contact_id="9", message="third")
    rows = svc.get_thread(db, contact_id="9", anchor_id=anchor.id)
    assert [r.message for r in rows] == ["first", "second", "third"]


# --------------------------------------------------------------------------- #
# Latency + breach filter                                                     #
# --------------------------------------------------------------------------- #
def test_outgoing_rows_carry_turn_latency(db):
    start = NOW - timedelta(minutes=5)
    _msg(db, sent_at=start, type="incoming", turn_id="t1", respond_ts=start)
    _msg(db, sent_at=start, type="outgoing", turn_id="t1", respond_ts=start + timedelta(seconds=6))

    rows, _ = svc.list_messages(db, now=NOW)
    out = [r for r in rows if r.type == "outgoing"][0]
    inc = [r for r in rows if r.type == "incoming"][0]
    assert out.latency_seconds == pytest.approx(6.0)
    assert inc.latency_seconds is None  # latency belongs to the reply, not the trigger


def test_breached_only_returns_both_sides_of_the_breaching_turn(db):
    """Deliberate: the filter keeps the incoming *and* the reply.

    A lone outgoing row would show a slow answer with no visible question, which is
    useless for triage — the first thing you want to know is what was asked.
    """
    fast = NOW - timedelta(minutes=10)
    slow = NOW - timedelta(minutes=5)
    _msg(db, sent_at=fast, type="incoming", turn_id="f", respond_ts=fast)
    _msg(db, sent_at=fast, type="outgoing", turn_id="f", respond_ts=fast + timedelta(seconds=2))
    _msg(db, sent_at=slow, type="incoming", turn_id="s", respond_ts=slow)
    _msg(db, sent_at=slow, type="outgoing", turn_id="s", respond_ts=slow + timedelta(seconds=45))

    rows, _ = svc.list_messages(db, now=NOW, breached_only=True, target_seconds=10)
    assert {r.turn_id for r in rows} == {"s"}          # fast turn excluded entirely
    assert sorted(r.type for r in rows) == ["incoming", "outgoing"]
    # Latency is still reported on the reply only.
    assert [r.latency_seconds for r in rows if r.type == "outgoing"] == [pytest.approx(45.0)]
    assert [r.latency_seconds for r in rows if r.type == "incoming"] == [None]


def test_breached_only_ignores_unresolved_rows(db):
    """No respond_ts means no honest latency — must not be reported as a breach."""
    t = NOW - timedelta(minutes=5)
    _msg(db, sent_at=t, type="incoming", turn_id="u", respond_ts=None)
    _msg(db, sent_at=t, type="outgoing", turn_id="u", respond_ts=None)
    rows, _ = svc.list_messages(db, now=NOW, breached_only=True, target_seconds=10)
    assert rows == []


# --------------------------------------------------------------------------- #
# Contact display — no opaque ids in the UI                                   #
# --------------------------------------------------------------------------- #
def test_display_name_prefers_stored_name(db):
    _msg(db, sent_at=NOW, first_name="Johnson", last_name=None, phone="+60165622487")
    rows, _ = svc.list_messages(db, now=NOW)
    assert rows[0].contact_display == "Johnson (+60165622487)"


def test_display_name_falls_back_to_phone_not_respond_id(db):
    _msg(db, sent_at=NOW, first_name=None, last_name=None, phone="+60165622487")
    rows, _ = svc.list_messages(db, now=NOW)
    assert rows[0].contact_display == "+60165622487"
    assert "445239409" not in rows[0].contact_display
