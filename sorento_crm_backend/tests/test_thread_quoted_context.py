"""Inbound quote context survives every lane that touches a thread message.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-L6 (a message that quotes an earlier one renders its quoted context
            above the body - read-side parity with Respond's own inbox)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S4.6)

Three lanes have to carry it or the FE has nothing to render:
  1. the external ingest (n8n forwards Respond's `replyTo` as
     reply_to_message_id / reply_to_message),
  2. the S4.8 Respond backfill (`persist_messages`), which used to keep the
     quoted ID and DROP the quoted text,
  3. the local fallback lane's item shape (`_row_to_item`).

Run:
    venv/bin/pytest tests/test_thread_quoted_context.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  (import first: app.dependencies alone is circular)
from app.dependencies import get_current_user_or_api_key, get_db, get_external_api_user
from app.models.chat_history import ChatHistory
from app.services import conversation_thread_service as svc
from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session

RESPOND_IO_ID = "ZZT437264484"
QUOTED_ID = "1780751880000000"
MESSAGE_ID = "1780751891000000"
INGEST_URL = "/api/v1/external/chat-history/messages"
NOW = datetime(2026, 8, 15, 9, 0, 0)

CONTACT = svc.ThreadContact(
    respond_io_id=RESPOND_IO_ID,
    phone_number="+60100000009",
    first_name="Zzt",
    last_name="Quoter",
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db):
    def _user():
        return {"id": "system"}

    def _db():
        yield db

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_current_user_or_api_key] = _user
    app.dependency_overrides[get_db] = _db
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


def _rows(db, message_id=MESSAGE_ID):
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.contact_id == RESPOND_IO_ID,
            ChatHistory.message_id == message_id,
        )
        .all()
    )


def _respond_item(message_id: str, *, text: str, reply_to: dict | None = None) -> dict:
    item = {
        "messageId": int(message_id),
        "traffic": "incoming",
        "message": {"type": "text", "text": text},
    }
    if reply_to is not None:
        item["replyTo"] = reply_to
    return item


# --------------------------------------------------------------------------- #
# Lane 1: the external ingest                                                  #
# --------------------------------------------------------------------------- #


def test_the_ingest_persists_both_the_quoted_id_and_the_quoted_text(client, db):
    response = client.post(
        INGEST_URL,
        json={
            "channel": "whatsapp",
            "contact_id": RESPOND_IO_ID,
            "phone_number": CONTACT.phone_number,
            "message": "Which courier?",
            "sent_at": 1780751906900,
            "type": "incoming",
            "message_id": MESSAGE_ID,
            "reply_to_message_id": QUOTED_ID,
            "reply_to_message": "Your order ships Tuesday.",
        },
    )

    assert response.status_code == 201
    row = _rows(db)[0]
    assert row.reply_to_message_id == QUOTED_ID
    assert row.reply_to_message == "Your order ships Tuesday.", (
        "the id alone cannot be shown to a reader - the excerpt IS the render"
    )


def test_a_replayed_ingest_does_not_lose_the_quote(client, db):
    """AC-J5 dedupe path: the second lane must not blank what the first stored."""
    body = {
        "channel": "whatsapp",
        "contact_id": RESPOND_IO_ID,
        "phone_number": CONTACT.phone_number,
        "message": "Which courier?",
        "sent_at": 1780751906900,
        "type": "incoming",
        "message_id": MESSAGE_ID,
        "reply_to_message_id": QUOTED_ID,
        "reply_to_message": "Your order ships Tuesday.",
    }
    client.post(INGEST_URL, json=body)
    client.post(INGEST_URL, json={**body, "reply_to_message_id": None, "reply_to_message": None})

    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].reply_to_message_id == QUOTED_ID
    assert rows[0].reply_to_message == "Your order ships Tuesday."


# --------------------------------------------------------------------------- #
# Lane 2: the Respond backfill                                                 #
# --------------------------------------------------------------------------- #


def test_the_respond_backfill_keeps_the_quoted_excerpt(db):
    written = svc.persist_messages(
        db,
        CONTACT,
        [
            _respond_item(
                MESSAGE_ID,
                text="Which courier?",
                reply_to={
                    "messageId": int(QUOTED_ID),
                    "traffic": "outgoing",
                    "message": {"type": "text", "text": "Your order ships Tuesday."},
                },
            )
        ],
    )

    assert written == 1
    row = _rows(db)[0]
    assert row.reply_to_message_id == QUOTED_ID
    assert row.reply_to_message == "Your order ships Tuesday."


def test_a_quoted_media_message_is_backfilled_as_a_typed_placeholder(db):
    svc.persist_messages(
        db,
        CONTACT,
        [
            _respond_item(
                MESSAGE_ID,
                text="Is this the right one?",
                reply_to={
                    "messageId": int(QUOTED_ID),
                    "message": {
                        "type": "attachment",
                        "attachment": {"type": "image", "fileName": "sink.jpg"},
                    },
                },
            )
        ],
    )

    row = _rows(db)[0]
    assert row.reply_to_message == "[image] sink.jpg", (
        "a quoted photo must read as something, not as an empty block"
    )


def test_a_message_with_no_quote_backfills_clean(db):
    svc.persist_messages(db, CONTACT, [_respond_item(MESSAGE_ID, text="just a message")])

    row = _rows(db)[0]
    assert row.reply_to_message_id is None
    assert row.reply_to_message is None


# --------------------------------------------------------------------------- #
# Lane 3: the local fallback item shape the FE renders                          #
# --------------------------------------------------------------------------- #


def test_the_local_lane_emits_the_replyto_object_the_chat_list_reads(db):
    row = ChatHistory(
        channel="whatsapp",
        contact_id=RESPOND_IO_ID,
        phone_number=CONTACT.phone_number,
        message="Which courier?",
        sent_at=NOW,
        type="incoming",
        message_id=MESSAGE_ID,
        reply_to_message_id=QUOTED_ID,
        reply_to_message="Your order ships Tuesday.",
    )
    db.add(row)
    db.flush()

    page = svc.fetch_thread_page(db, CONTACT, limit=10)
    item = next(i for i in page["items"] if str(i["messageId"]) == MESSAGE_ID)

    assert item["replyTo"]["messageId"] == QUOTED_ID
    assert item["replyTo"]["message"]["text"] == "Your order ships Tuesday."


def test_the_local_lane_emits_no_replyto_for_an_unquoted_message(db):
    db.add(
        ChatHistory(
            channel="whatsapp",
            contact_id=RESPOND_IO_ID,
            phone_number=CONTACT.phone_number,
            message="just a message",
            sent_at=NOW + timedelta(seconds=1),
            type="incoming",
            message_id=MESSAGE_ID,
        )
    )
    db.flush()

    page = svc.fetch_thread_page(db, CONTACT, limit=10)
    item = next(i for i in page["items"] if str(i["messageId"]) == MESSAGE_ID)

    assert item["replyTo"] is None
