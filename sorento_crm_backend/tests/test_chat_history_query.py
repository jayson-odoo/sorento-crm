"""Chat history admin listing: filters, keyset pagination, thread view.

Covers UAC OBS-S5-01 .. OBS-S5-12.

`chat_histories` is high-volume and its `contact_id` is the **Respond.io id string**,
not `respond_contacts.id` — so name resolution is a join, and the UI must never surface
the raw id (no opaque identifiers in the UI). Pagination is keyset on
`(sent_at, id)` because OFFSET degrades badly once the table is large.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.chat_history import ChatHistory
from app.services import chat_history_query as svc
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


NOW = datetime(2026, 7, 20, 12, 0, 0)


def _list(db, **kw):
    """Adapter: the grid uses offset paging; these behavioural tests only care about
    the returned rows, so normalise both paths to a (rows, _) shape."""
    kw.pop("cursor", None)
    limit = kw.pop("limit", 50)
    page = kw.pop("page", 1)
    rows, _total = svc.list_messages_page(db, page=page, limit=limit, **kw)
    return rows, None



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
    rows, _ = _list(db, date_from=NOW - timedelta(days=1), date_to=NOW)
    assert [r.message for r in rows] == ["recent"]


def test_default_window_is_last_24h(db):
    _msg(db, sent_at=NOW - timedelta(days=3), message="old")
    _msg(db, sent_at=NOW - timedelta(hours=2), message="recent")
    rows, _ = _list(db, now=NOW)
    assert [r.message for r in rows] == ["recent"]


def test_contact_filter(db):
    _msg(db, sent_at=NOW, contact_id="111", message="a")
    _msg(db, sent_at=NOW, contact_id="222", message="b")
    rows, _ = _list(db, contact_id="222", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["b"]


def test_direction_filter(db):
    _msg(db, sent_at=NOW, type="incoming", message="in")
    _msg(db, sent_at=NOW, type="outgoing", message="out")
    rows, _ = _list(db, direction="outgoing", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["out"]


def test_search_matches_message_text(db):
    _msg(db, sent_at=NOW, message="SRTKS2405 stock level")
    _msg(db, sent_at=NOW, message="how to submit complaint")
    rows, _ = _list(db, search="srtks", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert len(rows) == 1


def test_search_matches_phone(db):
    _msg(db, sent_at=NOW, phone="+60111111111", message="a")
    _msg(db, sent_at=NOW, phone="+60222222222", message="b")
    rows, _ = _list(db, search="222222", date_from=NOW - timedelta(hours=1), date_to=NOW + timedelta(hours=1))
    assert [r.message for r in rows] == ["b"]


# --------------------------------------------------------------------------- #
# Ordering + keyset pagination                                                #
# --------------------------------------------------------------------------- #
def test_newest_first(db):
    _msg(db, sent_at=NOW - timedelta(minutes=5), message="older")
    _msg(db, sent_at=NOW - timedelta(minutes=1), message="newer")
    rows, _ = _list(db, now=NOW)
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

    rows, _ = _list(db, now=NOW)
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

    rows, _ = _list(db, now=NOW, breached_only=True, target_seconds=10)
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
    rows, _ = _list(db, now=NOW, breached_only=True, target_seconds=10)
    assert rows == []


# --------------------------------------------------------------------------- #
# Contact display — no opaque ids in the UI                                   #
# --------------------------------------------------------------------------- #
def test_display_name_prefers_stored_name(db):
    _msg(db, sent_at=NOW, first_name="Johnson", last_name=None, phone="+60165622487")
    rows, _ = _list(db, now=NOW)
    assert rows[0].contact_display == "Johnson (+60165622487)"


def test_display_name_falls_back_to_phone_not_respond_id(db):
    _msg(db, sent_at=NOW, first_name=None, last_name=None, phone="+60165622487")
    rows, _ = _list(db, now=NOW)
    assert rows[0].contact_display == "+60165622487"
    assert "445239409" not in rows[0].contact_display


# --------------------------------------------------------------------------- #
# Offset paging (the grid path) — total + arbitrary page jump                 #
# --------------------------------------------------------------------------- #
def test_page_returns_total_for_the_filtered_set(db):
    for i in range(7):
        _msg(db, sent_at=NOW - timedelta(minutes=i), message=f"m{i}")
    rows, total = svc.list_messages_page(db, now=NOW, page=1, limit=3)
    assert total == 7
    assert len(rows) == 3


def test_page_jump_lands_on_the_right_slice(db):
    for i in range(7):
        _msg(db, sent_at=NOW - timedelta(minutes=i), message=f"m{i}")  # m0 newest
    p1, _ = svc.list_messages_page(db, now=NOW, page=1, limit=3)
    p3, _ = svc.list_messages_page(db, now=NOW, page=3, limit=3)
    assert [r.message for r in p1] == ["m0", "m1", "m2"]
    assert [r.message for r in p3] == ["m6"]  # last page, one row


def test_sort_ascending(db):
    _msg(db, sent_at=NOW - timedelta(minutes=5), message="older")
    _msg(db, sent_at=NOW - timedelta(minutes=1), message="newer")
    rows, _ = svc.list_messages_page(db, now=NOW, sort="sent_at", dir_="asc")
    assert [r.message for r in rows] == ["older", "newer"]


def test_breached_only_total_reflects_only_breached(db):
    slow = NOW - timedelta(minutes=5)
    fast = NOW - timedelta(minutes=8)
    _msg(db, sent_at=fast, type="incoming", turn_id="f", respond_ts=fast)
    _msg(db, sent_at=fast, type="outgoing", turn_id="f", respond_ts=fast + timedelta(seconds=2))
    _msg(db, sent_at=slow, type="incoming", turn_id="s", respond_ts=slow)
    _msg(db, sent_at=slow, type="outgoing", turn_id="s", respond_ts=slow + timedelta(seconds=45))
    rows, total = svc.list_messages_page(db, now=NOW, breached_only=True, target_seconds=10)
    assert total == 2  # both sides of the one breaching turn
    assert {r.turn_id for r in rows} == {"s"}


# --------------------------------------------------------------------------- #
# Grouping (OBS-S5-20)                                                        #
# --------------------------------------------------------------------------- #
class TestGroupByOrdering:
    """Grouping is a SERVER-ordering concern, not a rendering one.

    The listing is offset-paginated, so if the server does not make group members
    contiguous the frontend can only group within the current page — every page
    shows fragments of many groups and the header counts are wrong. So `group_by`
    selects the ordering; the frontend only draws the headers.

    Date needs no special ordering: `sent_at desc` already yields contiguous
    Malaysia calendar dates, because a fixed +8h offset preserves ordering.
    """

    def _seed(self, db):
        # Two contacts interleaved in time, so ordering by time and ordering by
        # contact produce visibly different sequences.
        # Anchored to NOW, not an independent literal: list_messages_page
        # applies a 24-hour default window, so rows pinned to a fixed date
        # silently fall outside it once real time moves past them and every
        # assertion here starts returning an empty page.
        base = NOW - timedelta(hours=1)
        rows = [
            ("+60111", "Ann", base + timedelta(minutes=0)),
            ("+60222", "Bob", base + timedelta(minutes=1)),
            ("+60111", "Ann", base + timedelta(minutes=2)),
            ("+60222", "Bob", base + timedelta(minutes=3)),
        ]
        for phone, name, ts in rows:
            db.add(
                ChatHistory(
                    channel="whatsapp",
                    contact_id=str(uuid.uuid4()),
                    phone_number=phone,
                    first_name=name,
                    message=f"{name} {ts:%H:%M}",
                    type="incoming",
                    sent_at=ts,
                )
            )
        db.commit()

    def test_default_is_time_ordered_and_interleaved(self, db):
        self._seed(db)
        rows, _ = svc.list_messages_page(db, now=NOW, limit=10)
        assert [r.phone_number for r in rows] == ["+60222", "+60111", "+60222", "+60111"]

    def test_group_by_contact_makes_each_contact_contiguous(self, db):
        self._seed(db)
        rows, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="contact")
        phones = [r.phone_number for r in rows]
        # Every contact appears as one unbroken run — the property the frontend
        # relies on to draw a header once per group.
        assert phones == sorted(phones)
        assert len(set(phones)) == 2

    def test_group_by_contact_keeps_messages_newest_first_within_a_contact(self, db):
        self._seed(db)
        rows, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="contact")
        ann = [r for r in rows if r.phone_number == "+60111"]
        assert [r.sent_at for r in ann] == sorted([r.sent_at for r in ann], reverse=True)

    def test_group_by_date_leaves_time_ordering_alone(self, db):
        """Dates are already contiguous under sent_at desc; re-ordering would
        only risk changing behaviour for no gain."""
        self._seed(db)
        default, _ = svc.list_messages_page(db, now=NOW, limit=10)
        by_date, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="date")
        assert [r.id for r in by_date] == [r.id for r in default]

    def test_contiguity_survives_pagination(self, db):
        """The real reason this is server-side: a group must not fragment across
        a page boundary."""
        self._seed(db)
        page1, total = svc.list_messages_page(db, now=NOW, page=1, limit=2, group_by="contact")
        page2, _ = svc.list_messages_page(db, now=NOW, page=2, limit=2, group_by="contact")
        assert total == 4
        assert {r.phone_number for r in page1} == {"+60111"}
        assert {r.phone_number for r in page2} == {"+60222"}

    def test_unknown_group_by_falls_back_to_default(self, db):
        self._seed(db)
        rows, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="nonsense")
        assert [r.phone_number for r in rows] == ["+60222", "+60111", "+60222", "+60111"]

    def test_grouping_composes_with_filters(self, db):
        self._seed(db)
        rows, total = svc.list_messages_page(db, now=NOW, limit=10, group_by="contact", search="Ann")
        assert total == 2
        assert {r.phone_number for r in rows} == {"+60111"}

    def test_contact_date_uses_contact_ordering(self, db):
        """contact_date is contact-outer/date-inner, so it needs the same
        contiguity as plain contact grouping — the date split is drawn inside
        each contact run by the frontend."""
        self._seed(db)
        by_contact, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="contact")
        by_both, _ = svc.list_messages_page(db, now=NOW, limit=10, group_by="contact_date")
        assert [r.id for r in by_both] == [r.id for r in by_contact]
