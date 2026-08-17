"""Internal ticket comments with @mention (UAC AC-L1, slice S4.3).

ROUTE-layer tests for the two new endpoints on the conversation-SLA router,
mirroring tests/test_intervention_ticket_detail_route.py:

  POST /{tracking_id}/comments   - create, assignee-or-manager scoped
  GET  /{tracking_id}/comments   - list, oldest first

Covered here: happy path, auth denial, out-of-scope viewer (404, never 403),
validation (empty body, unknown mentioned user), the in-app mention
notification, contact-scoped (Respond-ingested) comments showing in every open
ticket for that contact, and the hard rule that a comment NEVER reaches the
contact.

Run:
    venv/bin/pytest tests/test_ticket_comments.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.notification import Notification, NotificationDelivery
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.ticket_comment import ConversationTicketComment
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
BASE = "/api/v1/sla-management/conversation-sla-tracking"


class _NoMessagesRespondClient:
    """No Respond.io network calls. A comment must never touch a send path, so
    any attempt to message the contact from this suite is a hard failure."""

    def list_messages(self, identifier, limit=50, cursor=None):
        return {"items": []}

    def send_message(self, *a, **k):  # pragma: no cover - guarded, never called
        raise AssertionError("A comment must never send a message to the contact.")

    def create_comment(self, identifier, text):
        return {"id": "respond-comment-1"}


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.integration_service.RespondClient",
        lambda *a, **k: _NoMessagesRespondClient(),
    )
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _no_admins(monkeypatch):
    """No role tables are seeded - pin every actor as a non-admin so the
    outsider-scope tests exercise the real visibility branch."""
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())


@pytest.fixture(autouse=True)
def _no_respond_mirror(monkeypatch):
    """AC-L2's mirror is its own suite (test_ticket_comment_mirror.py). Here it
    is stubbed out so these tests measure the CRM source of truth only."""
    monkeypatch.setattr(
        "app.services.ticket_comment_service.mirror_comment_to_respond",
        lambda *a, **k: False,
    )


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
    outsider_id = str(uuid.uuid4())
    mentioned_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    db.add(User(id=outsider_id, email="outsider@test.com", name="Someone Else"))
    db.add(User(id=mentioned_id, email="lead@test.com", name="Team Lead"))
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
        "outsider_id": outsider_id,
        "mentioned_id": mentioned_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _create_ticket(db, seed, *, source_message_id="wamid.msg-1", **over):
    service = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id=source_message_id,
        source_message_text="Yes, please connect me to a person.",
        **over,
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


@pytest.fixture
def anon_client(db):
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _act_as(user_id: str) -> None:
    _ACTOR["id"] = user_id
    _ACTOR["name"] = "Test Actor"


# ---------------------------------------------------------------- happy path


def test_assignee_can_post_a_comment_and_read_it_back(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    created = client.post(
        f"{BASE}/{tracking.id}/comments",
        json={"body": "Checked the stock, waiting on the warehouse."},
    )

    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["body"] == "Checked the stock, waiting on the warehouse."
    assert payload["author_name"] == "Agent One"
    assert payload["source"] == "crm"
    assert payload["created_at"]

    listed = client.get(f"{BASE}/{tracking.id}/comments")
    assert listed.status_code == 200, listed.text
    items = listed.json()
    assert [c["body"] for c in items] == ["Checked the stock, waiting on the warehouse."]


def test_comments_come_back_oldest_first(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    for body in ("first", "second", "third"):
        assert client.post(f"{BASE}/{tracking.id}/comments", json={"body": body}).status_code == 201

    items = client.get(f"{BASE}/{tracking.id}/comments").json()
    assert [c["body"] for c in items] == ["first", "second", "third"]


def test_a_comment_never_reaches_the_contact(client, db):
    """The whole point of an internal note. The stub Respond client raises on
    send_message, so a comment that leaked onto a send path fails here."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    resp = client.post(f"{BASE}/{tracking.id}/comments", json={"body": "internal only"})

    assert resp.status_code == 201, resp.text


# ------------------------------------------------------------------- mention


def test_mentioned_user_gets_an_in_app_notification_with_a_deep_link(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    resp = client.post(
        f"{BASE}/{tracking.id}/comments",
        json={
            "body": "@Team Lead can you take a look?",
            "mentioned_user_ids": [seed["mentioned_id"]],
        },
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["mentioned_names"] == ["Team Lead"]

    note = (
        db.query(Notification)
        .filter(
            Notification.user_id == seed["mentioned_id"],
            Notification.type == "conversation_ticket_comment",
        )
        .one()
    )
    assert note.source_entity_type == "conversation_sla_tracking"
    assert str(note.source_entity_id) == str(tracking.id)
    assert str(tracking.id) in (note.body or ""), "the deep link must reach the ticket"
    channels = {
        d.channel
        for d in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == note.id)
        .all()
    }
    assert "in_app" in channels
    assert "email" not in channels, "AC-L1 is the in-app lane only"


def test_mentioning_yourself_notifies_nobody(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    resp = client.post(
        f"{BASE}/{tracking.id}/comments",
        json={"body": "@Agent One noting this for myself", "mentioned_user_ids": [seed["assignee_id"]]},
    )

    assert resp.status_code == 201, resp.text
    # Scoped to the comment notification: the ticket's own assignment notify
    # (fired by create_tracking in the fixture) is a different event entirely.
    assert (
        db.query(Notification)
        .filter(Notification.type == "conversation_ticket_comment")
        .count()
        == 0
    )


def test_a_failing_mention_notification_never_fails_the_comment(client, db, monkeypatch):
    """Post-commit side effects are best-effort (PRINCIPLES.md): the comment is
    already saved, so a notification blowing up must not 500 the caller."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    def _boom(*a, **k):
        raise RuntimeError("notification backend down")

    monkeypatch.setattr(
        "app.services.notification_service.NotificationService.create_with_channel_preferences",
        _boom,
    )

    resp = client.post(
        f"{BASE}/{tracking.id}/comments",
        json={"body": "@Team Lead ping", "mentioned_user_ids": [seed["mentioned_id"]]},
    )

    assert resp.status_code == 201, resp.text
    assert db.query(ConversationTicketComment).count() == 1


# ---------------------------------------------------------------- validation


def test_an_empty_comment_is_rejected(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    assert client.post(f"{BASE}/{tracking.id}/comments", json={"body": "   "}).status_code == 422
    assert client.post(f"{BASE}/{tracking.id}/comments", json={}).status_code == 422


def test_an_unknown_mentioned_user_is_rejected(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["assignee_id"])

    resp = client.post(
        f"{BASE}/{tracking.id}/comments",
        json={"body": "@Ghost hello", "mentioned_user_ids": [str(uuid.uuid4())]},
    )

    # 400 VALIDATION_ERROR: the app's own AppException flow, not FastAPI's
    # request-schema 422 (the id is well-formed, it just names nobody).
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert db.query(ConversationTicketComment).count() == 0


# ---------------------------------------------------------------------- auth


def test_no_principal_at_all_is_rejected(anon_client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)

    assert anon_client.get(f"{BASE}/{tracking.id}/comments").status_code in (401, 403)
    assert anon_client.post(
        f"{BASE}/{tracking.id}/comments", json={"body": "x"}
    ).status_code in (401, 403)


def test_outsider_gets_404_not_a_leak(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _act_as(seed["outsider_id"])

    posted = client.post(f"{BASE}/{tracking.id}/comments", json={"body": "nosy"})
    listed = client.get(f"{BASE}/{tracking.id}/comments")

    assert posted.status_code == 404, posted.text
    assert listed.status_code == 404, listed.text
    assert db.query(ConversationTicketComment).count() == 0


def test_unknown_tracking_id_is_404(client, db):
    seed = _seed(db)
    _act_as(seed["assignee_id"])

    assert client.get(f"{BASE}/{uuid.uuid4()}/comments").status_code == 404


# --------------------------------------------------- contact-scoped comments


def test_respond_side_comments_render_in_every_open_ticket_for_that_contact(client, db):
    """AC-L3: Respond comments are contact-scoped, not ticket-scoped. They carry
    no tracking_id and must therefore appear in each of the contact's tickets."""
    seed = _seed(db)
    first = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    second = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    db.add(
        ConversationTicketComment(
            id=str(uuid.uuid4()),
            tracking_id=None,
            respond_contact_id=seed["contact_id"],
            author_name="Inbox Agent",
            author_respond_user_id="777",
            body="Spoke to him on the phone.",
            source="respond",
            respond_comment_id="rc-1",
        )
    )
    db.commit()
    _act_as(seed["assignee_id"])

    for tracking in (first, second):
        items = client.get(f"{BASE}/{tracking.id}/comments").json()
        assert [c["body"] for c in items] == ["Spoke to him on the phone."]
        assert items[0]["source"] == "respond"
        assert items[0]["author_name"] == "Inbox Agent"


def test_a_crm_comment_stays_on_its_own_ticket(client, db):
    seed = _seed(db)
    first = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    second = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    _act_as(seed["assignee_id"])

    client.post(f"{BASE}/{first.id}/comments", json={"body": "about the first enquiry"})

    assert [c["body"] for c in client.get(f"{BASE}/{first.id}/comments").json()] == [
        "about the first enquiry"
    ]
    assert client.get(f"{BASE}/{second.id}/comments").json() == []
