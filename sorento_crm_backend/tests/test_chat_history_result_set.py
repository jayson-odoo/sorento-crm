"""chat_histories message_id/result columns + conversation-variables referenced_result_set.

- POST /external/chat-history/messages accepts optional message_id + result (back-compat without)
- POST /external/chat-history returns message_id + result per message
- GET /external/conversation-variables/{respond_io_id}?message_id=... injects
  session_vars.referenced_result_set (resolved result / null) response-only
- service get_referenced_result_set: match, no match, message without result

Run with:
    pytest tests/test_chat_history_result_set.py -v
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  (import first: app.dependencies alone is circular)
from app.dependencies import get_current_user_or_api_key, get_db, get_external_api_user
from app.models.access import RespondContact
from app.models.chat_history import ChatHistory
from app.services.conversation_variables_service import get_referenced_result_set
from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session

RESPOND_IO_ID = "437264483"
MESSAGE_ID = "1780751891000000"
RESULT_SET = [
    {
        "idx": 1,
        "uuid": None,
        "label": "Promotion: UPDATED SORENTO STOP VALVE PROMO_07052026 DEALER",
        "entity_type": None,
        "product": None,
        "attachment_type": None,
        "filename": None,
    }
]


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
    # Authorization is deliberately out of scope here: this suite mocks the
    # database, so the real RBAC lookup cannot answer. Enforcement is covered
    # by test_external_permission_guard / _coverage.
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_contact(db) -> None:
    db.add(
        RespondContact(
            id=str(uuid.uuid4()),
            respond_io_id=RESPOND_IO_ID,
            phone_number="+60166753328",
            session_vars={"flow": "promo", "last_result_set": [{"idx": 9}]},
        )
    )
    db.commit()


def _ingest_payload(**overrides) -> dict:
    payload = {
        "channel": "whatsapp",
        "contact_id": RESPOND_IO_ID,
        "phone_number": "+60166753328",
        "message": "I have attached the file(s) below.",
        "sent_at": 1780751906900,
        "first_name": "Jayson",
        "last_name": None,
        "type": "outgoing",
        "message_id": MESSAGE_ID,
        "result": RESULT_SET,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------- ingest


def test_ingest_persists_message_id_and_result(client, db):
    r = client.post("/api/v1/external/chat-history/messages", json=_ingest_payload())
    assert r.status_code == 201

    row = db.query(ChatHistory).filter(ChatHistory.id == r.json()["id"]).one()
    assert row.message_id == MESSAGE_ID
    stored = row.result
    if isinstance(stored, str):  # sqlite stores the json text param verbatim
        import json

        stored = json.loads(stored)
    assert stored == RESULT_SET


def test_ingest_without_message_id_and_result_back_compat(client, db):
    payload = _ingest_payload()
    payload.pop("message_id")
    payload.pop("result")
    r = client.post("/api/v1/external/chat-history/messages", json=payload)
    assert r.status_code == 201

    row = db.query(ChatHistory).filter(ChatHistory.id == r.json()["id"]).one()
    assert row.message_id is None
    assert row.result is None


# ------------------------------------------------- reply-to (CRM-002)


def test_ingest_incoming_persists_reply_to(client, db):
    """Incoming quote-reply carries reply_to_message_id/message onto the row."""
    payload = _ingest_payload(
        type="incoming",
        message="All",
        message_id=None,
        result=None,
        reply_to_message_id=MESSAGE_ID,
        reply_to_message="menu text the user replied to",
    )
    r = client.post("/api/v1/external/chat-history/messages", json=payload)
    assert r.status_code == 201

    row = db.query(ChatHistory).filter(ChatHistory.id == r.json()["id"]).one()
    assert row.reply_to_message_id == MESSAGE_ID
    assert row.reply_to_message == "menu text the user replied to"


def test_ingest_non_reply_stores_null_reply_to(client, db):
    """Normal (non-reply) incoming message defaults reply_to columns to NULL."""
    payload = _ingest_payload(type="incoming", message="hi", message_id=None, result=None)
    r = client.post("/api/v1/external/chat-history/messages", json=payload)
    assert r.status_code == 201

    row = db.query(ChatHistory).filter(ChatHistory.id == r.json()["id"]).one()
    assert row.reply_to_message_id is None
    assert row.reply_to_message is None


def test_reply_to_references_outgoing_message_id(client, db):
    """reply_to_message_id equals the message_id of an existing outgoing row (AC3)."""
    client.post("/api/v1/external/chat-history/messages", json=_ingest_payload())  # outgoing MESSAGE_ID
    reply = _ingest_payload(
        type="incoming", message="5", message_id=None, result=None,
        reply_to_message_id=MESSAGE_ID, reply_to_message=None,
    )
    rid = client.post("/api/v1/external/chat-history/messages", json=reply).json()["id"]

    reply_row = db.query(ChatHistory).filter(ChatHistory.id == rid).one()
    outgoing = (
        db.query(ChatHistory)
        .filter(ChatHistory.contact_id == RESPOND_IO_ID, ChatHistory.type == "outgoing")
        .one()
    )
    assert reply_row.reply_to_message_id == outgoing.message_id


def test_messages_read_returns_reply_to(client):
    client.post(
        "/api/v1/external/chat-history/messages",
        json=_ingest_payload(
            type="incoming", message="All", message_id=None, result=None,
            reply_to_message_id=MESSAGE_ID, reply_to_message="quoted",
        ),
    )
    r = client.post(
        "/api/v1/external/chat-history",
        json={"channel": "whatsapp", "contact_id": RESPOND_IO_ID, "limit": 10, "order": "asc"},
    )
    assert r.status_code == 200
    msg = r.json()["messages"][0]
    assert msg["reply_to_message_id"] == MESSAGE_ID
    assert msg["reply_to_message"] == "quoted"


# ---------------------------------------------------------------- read


def test_messages_read_returns_message_id_and_result(client):
    client.post("/api/v1/external/chat-history/messages", json=_ingest_payload())
    r = client.post(
        "/api/v1/external/chat-history",
        json={"channel": "whatsapp", "contact_id": RESPOND_IO_ID, "limit": 10, "order": "asc"},
    )
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["message_id"] == MESSAGE_ID
    assert msgs[0]["result"] == RESULT_SET


# ------------------------------------------- conversation-variables GET


def test_conversation_variables_without_message_id_unchanged(client, db):
    _seed_contact(db)
    r = client.get(f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}")
    assert r.status_code == 200
    sv = r.json()["session_vars"]
    assert sv["flow"] == "promo"
    assert "referenced_result_set" not in sv


def test_conversation_variables_injects_referenced_result_set(client, db):
    _seed_contact(db)
    client.post("/api/v1/external/chat-history/messages", json=_ingest_payload())

    r = client.get(
        f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
        params={"message_id": MESSAGE_ID},
    )
    assert r.status_code == 200
    sv = r.json()["session_vars"]
    assert sv["referenced_result_set"] == RESULT_SET
    # existing keys untouched; persisted session_vars not mutated by GET
    assert sv["last_result_set"] == [{"idx": 9}]
    contact = db.query(RespondContact).filter(RespondContact.respond_io_id == RESPOND_IO_ID).one()
    db.refresh(contact)
    assert "referenced_result_set" not in (contact.session_vars or {})


def test_conversation_variables_unknown_message_id_yields_null(client, db):
    _seed_contact(db)
    r = client.get(
        f"/api/v1/external/conversation-variables/{RESPOND_IO_ID}",
        params={"message_id": "999999"},
    )
    assert r.status_code == 200
    assert r.json()["session_vars"]["referenced_result_set"] is None


# ---------------------------------------------------------------- service


def test_get_referenced_result_set_message_without_result(client, db):
    payload = _ingest_payload(result=None)
    client.post("/api/v1/external/chat-history/messages", json=payload)
    assert (
        get_referenced_result_set(db, respond_io_id=RESPOND_IO_ID, message_id=MESSAGE_ID)
        is None
    )


def test_get_referenced_result_set_scoped_to_contact(client, db):
    client.post("/api/v1/external/chat-history/messages", json=_ingest_payload())
    assert (
        get_referenced_result_set(db, respond_io_id="other-contact", message_id=MESSAGE_ID)
        is None
    )
