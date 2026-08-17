"""POST /api/v1/sla-management/conversation-sla-tracking/{id}/ticket/send -
ROUTE-layer tests (UAC AC-D1).

tests/test_conversation_ticket_send.py covers the SERVICE with pre-built file
tuples, which is exactly why the multipart parsing defect below survived: the
route's ``isinstance(item, UploadFile)`` check used the FastAPI class while
``await request.form()`` yields ``starlette.datastructures.UploadFile``
(fastapi.UploadFile is a strict SUBCLASS of it), so the check never matched,
``files`` stayed empty, and an attached photo was silently delivered as a
text-only send. These tests go through the real route with real
``multipart/form-data`` bodies.

Respond.io HTTP + CRM storage are mocked throughout - no network, no upload.

Run:
    venv/bin/pytest tests/test_intervention_ticket_send_route.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
BASE = "/api/v1/sla-management/conversation-sla-tracking"


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
    """No role tables are seeded here - pin every actor as a non-admin so the
    scope check exercises the assignee branch, not an admin bypass."""
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())


def _seed(db, *, respond_io_id="10025531"):
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
            respond_io_id=respond_io_id,
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
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "assignee_id": assignee_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _create_ticket(db, seed, *, source_message_id="wamid.msg-1"):
    service = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id=source_message_id,
        source_message_text="Yes, please connect me to a person.",
    )
    return service.create_tracking(payload)


_ACTOR: dict = {"id": None}


@pytest.fixture
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _act_as(user_id: str) -> None:
    _ACTOR["id"] = user_id
    _ACTOR["name"] = "Agent One"


def _open_window(*_a, **_k):
    return {"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"}


def _fake_upload_chat_attachment(*, business_table, business_id, content, filename, mime):
    return {"url": f"https://cdn.test/{filename}", "kind": "image"}


class _FakeTextClient:
    def __init__(self):
        self.send_message_calls = []

    def send_message(self, identifier, text):
        self.send_message_calls.append((identifier, text))
        return {"id": "m-text"}


class _FakeAttachmentClient:
    def __init__(self):
        self.calls = []

    def send_attachment(self, identifier, attachment_type, url):
        self.calls.append((identifier, attachment_type, url))
        return {"id": f"m-attachment-{len(self.calls)}"}


def _respond_client_mock(text_client, attachment_client):
    mock_cls = MagicMock(return_value=text_client)
    mock_cls.for_identifier = MagicMock(return_value=attachment_client)
    return mock_cls


def test_multipart_file_is_delivered_as_an_attachment_not_silently_as_text(client, db):
    """The defect: a real multipart upload was parsed into an EMPTY file list,
    so the send degraded to the text-only branch and the photo never reached
    the contact (verified live: the outbox logged {"type": "text"})."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    text_client = _FakeTextClient()
    attachment_client = _FakeAttachmentClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(text_client, attachment_client),
    ):
        resp = client.post(
            f"{BASE}/{tracking.id}/ticket/send",
            data={"text": "here is the photo"},
            files=[("files", ("kitchen-sink.jpg", b"\xff\xd8\xff-not-really", "image/jpeg"))],
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent_as"] == "attachment"
    assert body["attachments"]["delivered"] == ["kitchen-sink.jpg"]
    assert body["attachments"]["failed"] is None
    assert len(attachment_client.calls) == 1
    # The caption still ships as its own text turn (existing contract).
    assert text_client.send_message_calls == [("10025531", "here is the photo")]


def test_multipart_send_with_several_files_delivers_all_of_them(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    attachment_client = _FakeAttachmentClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(_FakeTextClient(), attachment_client),
    ):
        resp = client.post(
            f"{BASE}/{tracking.id}/ticket/send",
            data={"text": ""},
            files=[
                ("files", ("a.pdf", b"a", "application/pdf")),
                ("files", ("b.pdf", b"b", "application/pdf")),
            ],
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent_as"] == "attachment"
    assert body["attachments"]["delivered"] == ["a.pdf", "b.pdf"]
    assert len(attachment_client.calls) == 2


def test_multipart_send_stamps_the_ticket_response_clock(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(_FakeTextClient(), _FakeAttachmentClient()),
    ):
        resp = client.post(
            f"{BASE}/{tracking.id}/ticket/send",
            data={"text": ""},
            files=[("files", ("a.pdf", b"a", "application/pdf"))],
        )

    assert resp.status_code == 200, resp.text
    db.refresh(tracking)
    assert tracking.is_responded is True
    assert tracking.responded_by == seed["assignee_id"]


def test_json_body_without_files_still_takes_the_text_path(client, db):
    """Regression guard for the JSON branch while the multipart branch changes."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    text_client = _FakeTextClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(text_client, _FakeAttachmentClient()),
    ):
        resp = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "just words"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent_as"] == "text"
    assert body["attachments"] is None
    assert text_client.send_message_calls == [("10025531", "just words")]
