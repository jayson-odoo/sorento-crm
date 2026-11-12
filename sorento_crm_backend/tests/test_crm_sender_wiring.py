"""N8N-RETIRE-A round 2: the CRM sender wired into the switch, the send, recovery, the
retry route, the settings API and the message-id link. Plan section 4c.

A fake client (tests/test_crm_sender.FakeClient) replaces RespondClient; `httpx.post` is
patched where the n8n path is asserted. No network. Postgres only, own seeds.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.models.chatbot_turn import ChatbotTurn
from app.models.integration import IntegrationLog
from app.models.user import SystemSetting
from tests._pg_fixture import TEST_PREFIX, blank_session
from tests.test_crm_sender import CONTACT, FakeClient, _NoClose, _status_error

SENDER_URL = "https://automate-zzt.example.com/webhook/chatbot-sender"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def factory(db):
    return lambda: _NoClose(db)


def _settings(db, **kw):
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co", **kw)
    db.add(row)
    db.commit()
    return row


def _turn(db, *, actions=None, status="processing", stage=None, trace=None, error=None):
    turn = ChatbotTurn(
        contact_respond_id=CONTACT,
        envelope={},
        status=status,
        stage=stage,
        error=error,
        trace=trace,
        response={"actions": actions} if actions is not None else None,
    )
    db.add(turn)
    db.commit()
    return str(turn.id)


def _crm_log(db, turn_id, step, status="success", message_id=None):
    payload = {"sender": "crm", "step": step, "kind": "send_message"}
    db.add(
        IntegrationLog(
            integration_channel="chatbot_sender",
            business_table="chatbot.turns",
            business_id=turn_id,
            direction="outbound",
            endpoint="respond.io",
            http_method="POST",
            request_payload=json.dumps(payload),
            status=status,
            status_code=200 if status == "success" else 400,
            error_message=None if status == "success" else "refused",
        )
    )
    db.commit()


TWO_PARTS = [{"kind": "send_message", "text": "A" * 3000 + "\n\n" + "B" * 3000}]


@pytest.fixture
def workspace(db):
    from app.schemas.respond_workspace import RespondWorkspaceCreate
    from app.services.respond_workspace_service import RespondWorkspaceService

    return RespondWorkspaceService(db).create(
        RespondWorkspaceCreate(space_id="ZZT-space-crm-sender", api_key="k", is_default=True)
    )


@pytest.fixture
def fake_respond(monkeypatch):
    """Route every RespondClient construction to one FakeClient."""
    from app.services.integration_service import RespondClient

    holder = {"client": FakeClient()}
    monkeypatch.setattr(
        RespondClient, "for_identifier", classmethod(lambda cls, db, ident: holder["client"])
    )
    return holder


@pytest.fixture
def session_patch(db, monkeypatch):
    """Code that opens its own SessionLocal gets the test session."""
    monkeypatch.setattr("app.database.SessionLocal", lambda: _NoClose(db))


# --------------------------------------------------------------------------- #
# 1. Settings columns
# --------------------------------------------------------------------------- #


def test_reply_sender_mode_defaults_to_n8n(db):
    row = _settings(db)
    db.refresh(row)
    assert row.chatbot_reply_sender_mode == "n8n"
    assert row.chatbot_reply_sender_contacts is None


# --------------------------------------------------------------------------- #
# 2. send_outcome follows the switch
# --------------------------------------------------------------------------- #


def _send_outcome(factory, turn_id):
    from app.services.chatbot import direct_ingress

    return direct_ingress.send_outcome(
        factory,
        turn_id=turn_id,
        contact_id=CONTACT,
        actions=[{"kind": "send_message", "text": "hi"}],
        reply={"text": "hi"},
        branch_kind=None,
    )


def _give_n8n_sender(db, workspace, monkeypatch):
    from app.utils.field_encryption import encrypt_secret

    # The sender pair has no field on RespondWorkspaceUpdate (a deliberate split), so the
    # columns are set directly, as tests/chatbot/test_direct_ingress.py does.
    workspace.chatbot_sender_url = SENDER_URL
    workspace.chatbot_sender_key_ciphertext = encrypt_secret("ZZT-key")
    db.commit()
    monkeypatch.setattr("app.services.chatbot.direct_ingress.assert_safe_outbound_url", lambda *a, **k: None)


def test_switch_n8n_posts_to_n8n_and_never_calls_crm_sender(db, factory, workspace, monkeypatch):
    from app.services.chatbot import crm_sender, direct_ingress

    _settings(db, chatbot_reply_sender_mode="n8n")
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock(return_value=httpx.Response(200, request=httpx.Request("POST", SENDER_URL)))
    monkeypatch.setattr(httpx, "post", post)
    crm = MagicMock()
    monkeypatch.setattr(crm_sender, "send", crm)

    turn_id = _turn(db)
    assert _send_outcome(factory, turn_id) == direct_ingress.SEND_OK
    post.assert_called_once()
    assert post.call_args.args[0] == SENDER_URL
    crm.assert_not_called()


def test_switch_covering_contact_uses_crm_sender_and_never_posts(db, factory, workspace, monkeypatch):
    from app.services.chatbot import crm_sender, direct_ingress

    _settings(db, chatbot_reply_sender_mode="contacts", chatbot_reply_sender_contacts=CONTACT)
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock()
    monkeypatch.setattr(httpx, "post", post)
    crm = MagicMock(return_value=direct_ingress.SEND_OK)
    monkeypatch.setattr(crm_sender, "send", crm)

    turn_id = _turn(db)
    assert _send_outcome(factory, turn_id) == direct_ingress.SEND_OK
    crm.assert_called_once()
    assert crm.call_args.kwargs["turn_id"] == turn_id
    post.assert_not_called()


def test_contact_not_listed_stays_on_n8n(db, factory, workspace, monkeypatch):
    from app.services.chatbot import crm_sender

    _settings(db, chatbot_reply_sender_mode="contacts", chatbot_reply_sender_contacts="somebody-else")
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock(return_value=httpx.Response(200, request=httpx.Request("POST", SENDER_URL)))
    monkeypatch.setattr(httpx, "post", post)
    crm = MagicMock()
    monkeypatch.setattr(crm_sender, "send", crm)

    _send_outcome(factory, _turn(db))
    post.assert_called_once()
    crm.assert_not_called()


def test_turn_already_sent_by_crm_stays_on_crm_after_switch_goes_back(db, factory, workspace, monkeypatch):
    from app.services.chatbot import crm_sender, direct_ingress

    _settings(db, chatbot_reply_sender_mode="n8n")
    _give_n8n_sender(db, workspace, monkeypatch)
    post = MagicMock()
    monkeypatch.setattr(httpx, "post", post)
    crm = MagicMock(return_value=direct_ingress.SEND_OK)
    monkeypatch.setattr(crm_sender, "send", crm)

    turn_id = _turn(db)
    _crm_log(db, turn_id, "0.0")
    assert _send_outcome(factory, turn_id) == direct_ingress.SEND_OK
    crm.assert_called_once()
    post.assert_not_called()


# --------------------------------------------------------------------------- #
# 3. sender_configured
# --------------------------------------------------------------------------- #


def test_sender_configured_true_when_crm_covers_contact_and_no_url(db, workspace):
    from app.services.chatbot import direct_ingress

    _settings(db, chatbot_reply_sender_mode="contacts", chatbot_reply_sender_contacts=CONTACT)
    assert direct_ingress.sender_configured(db, CONTACT) is True


def test_sender_configured_true_for_mode_all_without_a_contact(db, workspace):
    from app.services.chatbot import direct_ingress

    _settings(db, chatbot_reply_sender_mode="all")
    assert direct_ingress.sender_configured(db) is True


def test_sender_configured_false_with_n8n_switch_and_no_url(db, workspace):
    from app.services.chatbot import direct_ingress

    _settings(db, chatbot_reply_sender_mode="n8n")
    assert direct_ingress.sender_configured(db, CONTACT) is False


def test_sender_configured_false_for_an_unlisted_contact(db, workspace):
    from app.services.chatbot import direct_ingress

    _settings(db, chatbot_reply_sender_mode="contacts", chatbot_reply_sender_contacts="somebody-else")
    assert direct_ingress.sender_configured(db, CONTACT) is False


# --------------------------------------------------------------------------- #
# 5. Recovery on the CRM path
# --------------------------------------------------------------------------- #


def _dead_crm_row(db, *, steps):
    from app.services.chatbot import inbox_queue

    turn_id = _turn(
        db,
        actions=TWO_PARTS,
        stage=inbox_queue.SENDING_STAGE,
        trace=inbox_queue.INBOX_MARKER,
    )
    db.execute(text("UPDATE chatbot.turns SET finished_at = now() WHERE id = :i"), {"i": turn_id})
    db.commit()
    for step in steps:
        _crm_log(db, turn_id, step)
    return turn_id


def _recover(db, factory):
    from app.services.chatbot import inbox_queue

    inbox_queue._recover_dead_rows(CONTACT, factory)
    db.expire_all()


def test_recovery_flags_a_half_confirmed_crm_row_and_does_not_requeue(db, factory):
    from app.services.chatbot import inbox_queue

    turn_id = _dead_crm_row(db, steps=["0.0"])
    _recover(db, factory)
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one()
    assert row.status == "failed"
    assert row.stage == inbox_queue.SEND_UNCONFIRMED_STAGE
    assert row.status != inbox_queue.QUEUED


def test_recovery_marks_a_fully_confirmed_crm_row_done(db, factory):
    turn_id = _dead_crm_row(db, steps=["0.0", "0.1"])
    _recover(db, factory)
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one()
    assert row.status == "done"
    assert row.stage == "sent"


# --------------------------------------------------------------------------- #
# 6. Retry route
# --------------------------------------------------------------------------- #

TURNS_BASE = "/api/v1/system/chatbot/turns"


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow = {"system.chat_history.manage", "system.chat_history.view"}
    actor = {"id": str(uuid.uuid4()), "email": "retry@zzt.test", "name": "ZZT"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(allow))
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _failed_crm_turn(db):
    turn_id = _turn(db, actions=TWO_PARTS, status="failed", stage="send_unconfirmed", error="Not confirmed")
    _crm_log(db, turn_id, "0.0")
    return turn_id


def test_retry_on_crm_turn_resends_only_unconfirmed_steps(
    api, db, workspace, fake_respond, session_patch, monkeypatch
):
    from app.services.chatbot import dispatch

    _settings(db, chatbot_reply_sender_mode="all")
    reinject = MagicMock()
    monkeypatch.setattr(dispatch, "reinject_envelope", reinject)
    monkeypatch.setattr("app.api.v1.system.chatbot.reinject_envelope", reinject, raising=False)
    turn_id = _failed_crm_turn(db)

    resp = api.post(f"{TURNS_BASE}/{turn_id}/retry")
    assert resp.status_code == 200, resp.text
    fake = fake_respond["client"]
    assert fake.names() == ["send_message"]
    assert fake.calls[0][1][1] == "B" * 3000
    reinject.assert_not_called()
    db.expire_all()
    assert db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one().status == "done"


def test_retry_on_crm_turn_that_still_fails_keeps_it_failed_with_502(
    api, db, workspace, fake_respond, session_patch, monkeypatch
):
    _settings(db, chatbot_reply_sender_mode="all")
    fake_respond["client"] = FakeClient({0: _status_error(400)})
    turn_id = _failed_crm_turn(db)

    resp = api.post(f"{TURNS_BASE}/{turn_id}/retry")
    assert resp.status_code == 502, resp.text
    db.expire_all()
    assert db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one().status == "failed"


def test_retry_available_true_for_a_crm_turn_without_an_n8n_inject_url(api, db, workspace):
    _settings(db, chatbot_reply_sender_mode="n8n")
    _failed_crm_turn(db)
    resp = api.get(TURNS_BASE)
    assert resp.status_code == 200, resp.text
    assert resp.json()["retry_available"] is True


def test_retry_on_an_n8n_turn_keeps_todays_behaviour(api, db, workspace, fake_respond, monkeypatch):
    _settings(db, chatbot_reply_sender_mode="n8n")
    post = MagicMock()
    monkeypatch.setattr(httpx, "post", post)
    turn_id = _turn(
        db,
        actions=TWO_PARTS,
        status="failed",
        stage="understood",
        error="parser timed out",
    )
    resp = api.post(f"{TURNS_BASE}/{turn_id}/retry")
    assert resp.status_code == 409, resp.text  # no inject URL on the workspace, as today
    assert fake_respond["client"].calls == []
    post.assert_not_called()


# --------------------------------------------------------------------------- #
# 7. Settings API
# --------------------------------------------------------------------------- #

SETTINGS_URL = "/api/v1/user-management/settings/"
GENERAL_URL = "/api/v1/user-management/settings/general"


@pytest.fixture
def settings_api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow = {"user_management.settings.view", "user_management.settings.edit"}
    actor = {"id": str(uuid.uuid4()), "email": "settings@zzt.test", "name": "ZZT"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow
    )
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(allow))
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_settings_get_carries_the_reply_sender_fields(settings_api, db):
    _settings(db)
    body = settings_api.get(SETTINGS_URL).json()["settings"]
    assert body["chatbot_reply_sender_mode"] == "n8n"
    assert body["chatbot_reply_sender_contacts"] is None


def test_settings_put_saves_mode_and_contacts(settings_api, db):
    _settings(db)
    resp = settings_api.put(
        GENERAL_URL,
        json={
            "chatbot_reply_sender_mode": "contacts",
            "chatbot_reply_sender_contacts": "ZZT100000077\nZZT100000078",
        },
    )
    assert resp.status_code == 200, resp.text
    body = settings_api.get(SETTINGS_URL).json()["settings"]
    assert body["chatbot_reply_sender_mode"] == "contacts"
    assert body["chatbot_reply_sender_contacts"] == "ZZT100000077\nZZT100000078"


@pytest.mark.parametrize("bad", ["on", "CRM", "everyone", ""])
def test_settings_put_rejects_a_bad_mode(settings_api, db, bad):
    _settings(db)
    resp = settings_api.put(GENERAL_URL, json={"chatbot_reply_sender_mode": bad})
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------- #
# 8. Message id link
# --------------------------------------------------------------------------- #


class FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def _put(self, key, value):
        self.store[key] = value if isinstance(value, bytes) else str(value).encode()
        return True

    def set(self, key, value, ex=None, *a, **k):
        return self._put(key, value)

    def setex(self, key, ttl, value):
        return self._put(key, value)

    def get(self, key):
        return self.store.get(key)


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr("app.services.queue_service.redis_conn", r)
    for mod in (
        "app.services.chatbot.crm_sender",
        "app.api.v1.public.respond_webhook",
        "app.services.chat_history_ingest_service",
    ):
        try:
            monkeypatch.setattr(f"{mod}.redis_conn", r, raising=False)
        except (ImportError, AttributeError):
            pass
    return r


def _seed_outgoing_chat_row(db, message_id="123"):
    db.execute(
        text(
            "INSERT INTO chat_histories (channel, contact_id, phone_number, message, sent_at, "
            "type, message_id) VALUES ('whatsapp', :c, '+60100000000', 'hello', now(), "
            "'outgoing', :m)"
        ),
        {"c": CONTACT, "m": message_id},
    )
    db.commit()


def test_confirmed_step_links_the_respond_message_id_to_the_turn(db, factory, fake_redis):
    from app.services.chatbot import crm_sender

    turn_id = _turn(db)
    _seed_outgoing_chat_row(db)
    fake = FakeClient(message_id=123)
    crm_sender.send(
        factory,
        turn_id=turn_id,
        contact_id=CONTACT,
        actions=[{"kind": "send_message", "text": "hello"}],
        client=fake,
    )
    rows = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.business_id == turn_id, IntegrationLog.integration_channel == "chatbot_sender")
        .all()
    )
    assert len(rows) == 1 and "123" in (rows[0].response_payload or "")
    assert fake_redis.store.get("chatbot:sent-msg:123") == turn_id.encode()
    linked = db.execute(
        text("SELECT chatbot_turn_id FROM chat_histories WHERE contact_id = :c AND message_id = '123'"),
        {"c": CONTACT},
    ).scalar()
    assert linked == turn_id


def test_link_leaves_an_already_linked_chat_row_alone(db, factory, fake_redis):
    from app.services.chatbot import crm_sender

    turn_id = _turn(db)
    _seed_outgoing_chat_row(db)
    other = str(uuid.uuid4())
    db.execute(text("UPDATE chat_histories SET chatbot_turn_id = :t WHERE message_id = '123'"), {"t": other})
    db.commit()
    crm_sender.send(
        factory,
        turn_id=turn_id,
        contact_id=CONTACT,
        actions=[{"kind": "send_message", "text": "hello"}],
        client=FakeClient(message_id=123),
    )
    assert (
        db.execute(text("SELECT chatbot_turn_id FROM chat_histories WHERE message_id = '123'")).scalar()
        == other
    )


def test_redis_down_does_not_fail_the_send(db, factory, monkeypatch):
    from app.services.chatbot import crm_sender, direct_ingress

    class Down:
        def set(self, *a, **k):
            raise ConnectionError("redis down")

        setex = get = set

    monkeypatch.setattr("app.services.queue_service.redis_conn", Down())
    monkeypatch.setattr("app.services.chatbot.crm_sender.redis_conn", Down(), raising=False)
    turn_id = _turn(db)
    result = crm_sender.send(
        factory,
        turn_id=turn_id,
        contact_id=CONTACT,
        actions=[{"kind": "send_message", "text": "hello"}],
        client=FakeClient(message_id=123),
    )
    assert result == direct_ingress.SEND_OK


def _sent_event(message_id=123):
    return {
        "event_type": "message.sent",
        "contact": {"id": CONTACT, "phone": "+60100000000", "firstName": "Z"},
        "channel": {"source": "whatsapp"},
        "message": {
            "messageId": message_id,
            "traffic": "outgoing",
            "timestamp": 1760000000000,
            "message": {"type": "text", "text": "hello"},
        },
    }


def test_webhook_picks_the_turn_id_from_the_redis_key(db, fake_redis):
    from app.api.v1.public.respond_webhook import map_webhook_message

    turn_id = str(uuid.uuid4())
    fake_redis.store["chatbot:sent-msg:123"] = turn_id.encode()
    row = map_webhook_message(_sent_event(), db)
    assert row is not None and row.type == "outgoing"
    assert row.chatbot_turn_id == turn_id


def test_webhook_without_a_redis_key_leaves_the_turn_id_empty(db, fake_redis):
    from app.api.v1.public.respond_webhook import map_webhook_message

    row = map_webhook_message(_sent_event(777), db)
    assert row is not None
    assert row.chatbot_turn_id is None
