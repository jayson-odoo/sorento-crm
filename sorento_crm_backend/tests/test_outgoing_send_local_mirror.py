"""A CRM send writes its own `chat_histories` row (PLAN-optimistic-send, UAC section A).

The thread renders from the local table, and until now a CRM reply only reached
it via Respond -> n8n -> `/external/chat-history/messages`. These tests pin the
anchor the FE pending bubble relies on: the row is there when the send returns,
the later mirror dedupes onto it, and nothing about it can fail the send.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.chat_history import ChatHistory
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services import conversation_event_bus
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
RESPOND_IO_ID = "10025531"
BASE = "/api/v1/sla-management/conversation-sla-tracking"
INBOX = "/api/v1/sla-management/conversations"
# Respond mints messageId as epoch MICROseconds; the read lane keys its clock off it.
MSG_US = 1_787_640_441_538_436
MSG_US_2 = MSG_US + 1_000_000


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _no_admins(monkeypatch):
    """Non-admin actors with every permission: the drawer gate is the assignee
    check, the inbox gate is the reply permission - neither is under test here."""
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )


@pytest.fixture
def pokes(monkeypatch):
    """Every conversation event published, captured instead of sent."""
    seen: list[dict] = []

    def _publish(event_type, **kwargs):
        seen.append({"type": event_type, **kwargs})
        return True

    monkeypatch.setattr(conversation_event_bus, "publish", _publish)
    return seen


def _seed(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="NORMAL", name="Normal"))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id,
            phone_number=PHONE,
            name="Aisyah Rahman",
            first_name="Aisyah",
            last_name="Rahman",
            respond_io_id=RESPOND_IO_ID,
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="CS_AGENT", name="CS Agent"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="Customer Service - Tier 1"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="cs_general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.commit()
    return {"policy_id": policy_id, "contact_id": contact_id, "assignee_id": assignee_id}


def _create_ticket(db, seed):
    service = ConversationSLATrackingService(db)
    return service.create_tracking(
        ConversationSLATrackingCreate(
            agent_code="CS_AGENT",
            team_set_code="cs_general",
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id="wamid.msg-1",
            source_message_text="Yes, please connect me to a person.",
        )
    )


_ACTOR: dict = {"id": None}


@pytest.fixture
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_external_api_user

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "system", "role": "system"}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _act_as(user_id: str) -> None:
    _ACTOR["id"] = user_id
    _ACTOR["name"] = "Agent One"


def _open_window(*_a, **_k):
    return {"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"}


def _fake_upload(*, business_table, business_id, content, filename, mime):
    return {"url": f"https://cdn.test/{filename}", "kind": "image"}


class _TextClient:
    def __init__(self, ids):
        self.ids = list(ids)
        self.calls = []

    def send_message(self, identifier, text):
        self.calls.append((identifier, text))
        return {"messageId": self.ids.pop(0)}


class _AttachmentClient:
    def __init__(self, ids):
        self.ids = list(ids)
        self.calls = []

    def send_attachment(self, identifier, attachment_type, url):
        self.calls.append((identifier, attachment_type, url))
        return {"messageId": self.ids.pop(0)}


def _respond(text_client, attachment_client=None):
    mock_cls = MagicMock(return_value=text_client)
    mock_cls.for_identifier = MagicMock(return_value=attachment_client or _AttachmentClient([]))
    return mock_cls


def _rows(db):
    return (
        db.query(ChatHistory)
        .filter(ChatHistory.contact_id == RESPOND_IO_ID)
        .order_by(ChatHistory.id.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# AC-A1 / AC-A6: a text send from the drawer leaves the row and pokes the contact
# ---------------------------------------------------------------------------


def test_drawer_text_send_writes_the_outgoing_row_at_once(client, db, pokes):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])
    assert _rows(db) == []

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient([MSG_US]))
    ):
        resp = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "on my way"})

    assert resp.status_code == 200, resp.text
    rows = _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.type == "outgoing"
    assert row.message == "on my way"
    assert row.message_id == str(MSG_US)
    assert row.channel == "whatsapp"
    assert row.phone_number == PHONE
    # Respond's clock, read off its own id (microseconds).
    assert row.sent_at.isoformat(timespec="milliseconds") == "2026-08-25T06:47:21.538"
    assert row.respond_ts == row.sent_at
    assert [p for p in pokes if p["type"] == "message" and p.get("contact_id") == RESPOND_IO_ID]


# ---------------------------------------------------------------------------
# AC-A1 on the inbox lane (unstamped: no open ticket of the sender's)
# ---------------------------------------------------------------------------


def test_inbox_reply_without_a_ticket_writes_the_outgoing_row(client, db, pokes):
    seed = _seed(db)
    _act_as(seed["assignee_id"])

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient([MSG_US]))
    ):
        resp = client.post(f"{INBOX}/{seed['contact_id']}/reply", json={"text": "hello from inbox"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["stamped_ticket_id"] is None
    rows = _rows(db)
    assert [(r.type, r.message, r.message_id) for r in rows] == [
        ("outgoing", "hello from inbox", str(MSG_US))
    ]


# ---------------------------------------------------------------------------
# AC-A2 / AC-B4: caption + attachment = two rows, attachment as the read lane's placeholder
# ---------------------------------------------------------------------------


def test_attachment_send_writes_one_row_per_message(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment", _fake_upload
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond(_TextClient([MSG_US]), _AttachmentClient([MSG_US_2])),
    ):
        resp = client.post(
            f"{BASE}/{tracking.id}/ticket/send",
            data={"text": "here is the photo"},
            files=[("files", ("kitchen-sink.jpg", b"\xff\xd8\xff-not-really", "image/jpeg"))],
        )

    assert resp.status_code == 200, resp.text
    rows = _rows(db)
    assert [(r.type, r.message, r.message_id) for r in rows] == [
        ("outgoing", "here is the photo", str(MSG_US)),
        ("outgoing", "[image] kitchen-sink.jpg", str(MSG_US_2)),
    ]


# ---------------------------------------------------------------------------
# AC-A3: the mirror that arrives later lands on the same row
# ---------------------------------------------------------------------------


def test_the_later_mirror_dedupes_onto_the_local_row(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient([MSG_US]))
    ):
        assert client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "on my way"}).status_code == 200

    mirrored = client.post(
        "/api/v1/external/chat-history/messages",
        json={
            "channel": "whatsapp",
            "contact_id": RESPOND_IO_ID,
            "phone_number": PHONE,
            "message": "on my way",
            "sent_at": MSG_US // 1000,
            "type": "outgoing",
            "message_id": str(MSG_US),
            "turn_id": "turn-7",
        },
    )
    assert mirrored.status_code == 201, mirrored.text
    assert mirrored.json()["status"] == "duplicate"
    rows = _rows(db)
    assert len(rows) == 1
    # The mirror's richer field still lands (COALESCE upsert), on the one row.
    assert rows[0].turn_id == "turn-7"


# ---------------------------------------------------------------------------
# AC-A4: an acknowledgement whose id is not a timestamp writes nothing, breaks nothing
# ---------------------------------------------------------------------------


def test_non_timestamp_message_id_writes_no_row_and_the_send_still_succeeds(client, db, pokes):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient(["m-text"]))
    ):
        resp = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "on my way"})

    assert resp.status_code == 200, resp.text
    assert _rows(db) == []
    assert not [p for p in pokes if p["type"] == "message"]


# ---------------------------------------------------------------------------
# AC-A5: the local write failing is logged, never surfaced
# ---------------------------------------------------------------------------


def test_local_write_failure_never_fails_the_send(client, db, monkeypatch):
    from app.services import conversation_thread_service

    def _boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(conversation_thread_service, "persist_messages", _boom)
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    with patch("app.services.respond_messaging_service.get_window_state", _open_window), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient([MSG_US]))
    ):
        resp = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "on my way"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["sent_as"] == "text"
    assert _rows(db) == []


# ---------------------------------------------------------------------------
# AC-A7: a closed-window send that went out as a template mirrors the rendered body
# ---------------------------------------------------------------------------


def test_template_send_mirrors_the_rendered_body(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    def _closed_window(*_a, **_k):
        return {"open": False, "last_incoming_at": None, "checked_at": "", "source": "x"}

    def _fake_template(db_, *, identifier, use_case, context_vars, **_k):
        # The shape `send_template_for_use_case` really returns: the chat send
        # renders `body_text` over `params` itself to get the contact-visible text.
        return {
            "response": {"messageId": MSG_US},
            "template_name": "conversation_chat_v1",
            "template_id": "tpl-1",
            "params": [context_vars["message"]],
            "request_payload": {"message": {"body_text": "Hi, {{1}}"}},
        }

    with patch("app.services.respond_messaging_service.get_window_state", _closed_window), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", _fake_template
    ), patch(
        "app.services.respond_template_service.get_default_row", lambda db_, uc: None
    ), patch(
        "app.services.respond_template_service.serialize_default",
        lambda uc, row: {"is_valid": True},
    ), patch(
        "app.services.integration_service.RespondClient", _respond(_TextClient([]))
    ):
        resp = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "on my way"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["sent_as"] == "template"
    rows = _rows(db)
    assert [(r.type, r.message, r.message_id) for r in rows] == [
        ("outgoing", "Hi, on my way", str(MSG_US))
    ]
