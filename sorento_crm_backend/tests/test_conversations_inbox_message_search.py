"""The Conversations inbox search also finds MESSAGE TEXT (lane CONVO-SEARCH-MESSAGES).

Plan: documentation/plans/sla/PLAN-convo-search-messages-30oct.md

Owner, 30 Oct 2026: "i think from here need to be able to search by messages". The one box
that matched contact name / phone now also matches any stored message, inbound or outbound.

Pinned here:

1. A contact whose name or phone matches reads exactly as before (`match` is null).
2. Otherwise the newest matching message rides on the row as `match` (id, time, direction,
   snippet), and message-only rows sort newest MATCH first.
3. The tab and the `view_own` scope still decide who is on the list.
4. A sign-in code is never searchable: the match runs on the OTP-masked text.
5. It stays one statement per page, and paging over matches loses nothing.

Run:
    venv/bin/pytest tests/test_conversations_inbox_message_search.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import insert, select

from app.models.access import RespondContact
from app.models.chat_history import ChatHistory
from tests.test_conversations_inbox_list import (  # noqa: F401 - pytest fixtures
    BASE,
    _StatementCounter,
    _contact,
    _permissions,
    _ticket,
    _user,
    client,
    db,
    world,
)

T0 = datetime(2026, 8, 10, 8, 0, 0)


def _msg(db, rio: str, body: str, sent_at: datetime, *, direction: str = "incoming",
         message_id: str | None = "auto", channel: str = "whatsapp") -> str | None:
    mid = uuid.uuid4().hex[:16] if message_id == "auto" else message_id
    db.add(
        ChatHistory(
            channel=channel,
            contact_id=rio,
            phone_number="+60119999999",
            message=body,
            sent_at=sent_at,
            type=direction,
            message_id=mid,
        )
    )
    db.commit()
    return mid


def _search(client, q: str, tab: str = "all") -> list[dict]:
    res = client.get(BASE, params={"tab": tab, "q": q})
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _names(items) -> list[str]:
    return [row["name"] for row in items]


def test_an_incoming_message_finds_its_contact_with_the_match_on_the_row(client, db, world):
    mid = _msg(db, "zzt-io-4", "Boss, harga sofa 3 seater berapa?", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-4", "ok thanks", T0 + timedelta(hours=2))

    items = _search(client, "SOFA 3")
    assert _names(items) == ["ZZT Stranger"]
    row = items[0]
    assert row["match"]["message_id"] == mid
    assert row["match"]["direction"] == "incoming"
    assert row["match"]["sent_at"].startswith("2026-08-10T09:00:00")
    assert "sofa 3 seater" in row["match"]["snippet"]
    # The last message is still the last message: the row says both.
    assert row["last_message_snippet"] == "ok thanks"


def test_an_outgoing_message_matches_too(client, db, world):
    mid = _msg(db, "zzt-io-2", "Quotation sent, please check", T0 + timedelta(hours=1),
               direction="outgoing")
    items = _search(client, "quotation")
    assert _names(items) == ["ZZT Unassigned"]
    assert items[0]["match"]["message_id"] == mid
    assert items[0]["match"]["direction"] == "outgoing"


def test_chinese_and_malay_text_match_as_plain_substrings(client, db, world):
    _msg(db, "zzt-io-1", "请问这个沙发多少钱", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-3", "Saya nak tanya pasal katil", T0 + timedelta(hours=1))
    assert _names(_search(client, "沙发")) == ["ZZT Mine"]
    assert _names(_search(client, "katil")) == ["ZZT Mentioned"]


def test_a_name_match_reads_as_before_even_when_a_message_also_matches(client, db, world):
    _msg(db, "zzt-io-4", "the stranger things box set", T0 + timedelta(hours=1))
    items = _search(client, "stranger")
    assert _names(items) == ["ZZT Stranger"]
    assert items[0]["match"] is None


def test_the_row_carries_the_newest_matching_message(client, db, world):
    _msg(db, "zzt-io-4", "delivery tomorrow?", T0 + timedelta(hours=1))
    newest = _msg(db, "zzt-io-4", "delivery confirmed", T0 + timedelta(hours=3))
    _msg(db, "zzt-io-4", "thank you", T0 + timedelta(hours=4))
    items = _search(client, "delivery")
    assert items[0]["match"]["message_id"] == newest


def test_message_matches_sort_newest_match_first_not_newest_conversation(client, db, world):
    # Mine matched LONG ago but talked most recently; Stranger matched recently.
    _msg(db, "zzt-io-1", "warranty question", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-1", "unrelated and newest", T0 + timedelta(hours=9))
    _msg(db, "zzt-io-4", "warranty claim", T0 + timedelta(hours=5))
    assert _names(_search(client, "warranty")) == ["ZZT Stranger", "ZZT Mine"]


def test_the_active_tab_still_decides_who_is_listed(client, db, world):
    _msg(db, "zzt-io-1", "need a cabinet", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-4", "need a cabinet too", T0 + timedelta(hours=2))
    assert _names(_search(client, "cabinet", tab="mine")) == ["ZZT Mine"]
    assert _names(_search(client, "cabinet", tab="unassigned")) == []
    assert _names(_search(client, "cabinet", tab="all")) == ["ZZT Stranger", "ZZT Mine"]


def test_mentioned_tab_filters_by_message_text_too(client, db, world):
    _msg(db, "zzt-io-3", "sample request please", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-4", "sample request also", T0 + timedelta(hours=2))
    items = _search(client, "sample request", tab="mentioned")
    assert _names(items) == ["ZZT Mentioned"]
    assert items[0]["match"] is not None


def test_view_own_scope_still_narrows_a_message_search(db, world):
    from app.services import conversation_inbox_service as inbox

    _msg(db, "zzt-io-1", "dining table", T0 + timedelta(hours=1))
    _msg(db, "zzt-io-4", "dining table", T0 + timedelta(hours=2))
    only_mine = select(RespondContact.id).where(RespondContact.id == world["mine"])
    page = inbox.list_conversations(
        db, viewer_user_id=world["me"], tab="all", q="dining", contact_ids=only_mine
    )
    assert _names(page["items"]) == ["ZZT Mine"]


def test_a_sign_in_code_is_not_searchable(client, db, world):
    _msg(db, "zzt-io-4", "Your Sorento sign-in code is 482913", T0 + timedelta(hours=1),
         direction="outgoing")
    assert _search(client, "482913") == []
    items = _search(client, "sign-in code")
    assert _names(items) == ["ZZT Stranger"]
    assert "482913" not in items[0]["match"]["snippet"]


def test_a_message_without_an_id_is_not_a_match(client, db, world):
    """The thread jumps to a match by message id; a match it cannot open is not a result."""
    _msg(db, "zzt-io-4", "orphan wardrobe", T0 + timedelta(hours=1), message_id=None)
    assert _search(client, "wardrobe") == []


def test_a_message_on_another_channel_is_not_a_match(client, db, world):
    """The thread reads the WhatsApp channel only, so it could not open this match."""
    _msg(db, "zzt-io-4", "bookshelf enquiry", T0 + timedelta(hours=1), channel="telegram")
    assert _search(client, "bookshelf") == []


def test_a_digit_search_still_finds_ordinary_messages(client, db, world):
    _msg(db, "zzt-io-4", "my order SO-77123 arrived", T0 + timedelta(hours=1))
    assert _names(_search(client, "77123")) == ["ZZT Stranger"]


def test_the_snippet_keeps_the_term_near_the_front_of_a_long_message(client, db, world):
    """The row is ONE truncated line; a long lead would hide the hit behind the ellipsis."""
    body = "Hi boss, " + "lorem ipsum dolor sit amet " * 6 + "the ottoman is torn, " + "x " * 80
    _msg(db, "zzt-io-4", body, T0 + timedelta(hours=1))
    snippet = _search(client, "ottoman")[0]["match"]["snippet"]
    assert snippet.startswith("…")
    assert snippet.index("ottoman") <= 20


def test_wildcards_in_a_message_search_are_literal(client, db, world):
    _msg(db, "zzt-io-4", "50% discount", T0 + timedelta(hours=1))
    assert _names(_search(client, "50%")) == ["ZZT Stranger"]
    assert _search(client, "5_%") == []


def test_paging_over_message_matches_is_one_query_and_loses_nothing(db):
    from app.services import conversation_inbox_service as inbox

    contacts, messages = [], []
    for i in range(90):
        rio = f"zzt-msrch-{i:03d}"
        contacts.append({"id": str(uuid.uuid4()), "phone_number": f"+6018{i:07d}",
                         "name": f"ZZT Search {i:03d}", "respond_io_id": rio, "session_vars": {}})
        # Every 6th match shares its timestamp with the previous one: real keyset ties.
        stamp = T0 + timedelta(minutes=i - (1 if i % 6 == 0 and i else 0))
        messages.append({"channel": "whatsapp", "contact_id": rio, "phone_number": "+60",
                         "message": f"looking for a recliner #{i}", "sent_at": stamp,
                         "type": "incoming", "message_id": f"zzt-m-{i}"})
        messages.append({"channel": "whatsapp", "contact_id": rio, "phone_number": "+60",
                         "message": "later small talk", "sent_at": stamp + timedelta(days=1),
                         "type": "incoming", "message_id": f"zzt-m-{i}-b"})
    db.execute(insert(RespondContact), contacts)
    db.execute(insert(ChatHistory), messages)
    db.commit()
    viewer = _user(db, "msrch")

    seen, stamps, cursor, pages = [], [], None, 0
    while True:
        with _StatementCounter(db.get_bind()) as counted:
            page = inbox.list_conversations(
                db, viewer_user_id=viewer, tab="all", q="recliner", cursor=cursor, limit=20
            )
        assert len(counted.statements) == 1
        pages += 1
        seen.extend(row["contact_ref"] for row in page["items"])
        stamps.extend(row["match"]["sent_at"] for row in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
        assert pages < 20
    assert len(seen) == len(set(seen)) == 90
    assert stamps == sorted(stamps, reverse=True)


def test_paging_interleaves_name_hits_and_message_hits_without_gaps(db):
    """Name hits sort by last message, message hits by match time, on ONE keyset."""
    from app.services import conversation_inbox_service as inbox

    contacts, messages = [], []
    for i in range(40):
        rio = f"zzt-mix-{i:03d}"
        by_name = i % 2 == 0
        contacts.append({"id": str(uuid.uuid4()), "phone_number": f"+6017{i:07d}",
                         "name": f"ZZT Ottoman {i:03d}" if by_name else f"ZZT Plain {i:03d}",
                         "respond_io_id": rio, "session_vars": {}})
        stamp = T0 + timedelta(minutes=3 * i)
        body = "small talk" if by_name else "about the ottoman"
        messages.append({"channel": "whatsapp", "contact_id": rio, "phone_number": "+60",
                         "message": body, "sent_at": stamp, "type": "incoming",
                         "message_id": f"zzt-x-{i}"})
        # Message hits get a LATER non-matching message, so their last message
        # time and their match time disagree.
        if not by_name:
            messages.append({"channel": "whatsapp", "contact_id": rio, "phone_number": "+60",
                             "message": "later", "sent_at": stamp + timedelta(days=2),
                             "type": "incoming", "message_id": f"zzt-x-{i}-b"})
    db.execute(insert(RespondContact), contacts)
    db.execute(insert(ChatHistory), messages)
    db.commit()
    viewer = _user(db, "mix")

    seen, keys, cursor = [], [], None
    while True:
        page = inbox.list_conversations(
            db, viewer_user_id=viewer, tab="all", q="ottoman", cursor=cursor, limit=7
        )
        for row in page["items"]:
            seen.append(row["contact_ref"])
            keys.append(row["match"]["sent_at"] if row["match"] else row["last_message_at"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(f"zzt-mix-{i:03d}" for i in range(40))
    assert keys == sorted(keys, reverse=True)
