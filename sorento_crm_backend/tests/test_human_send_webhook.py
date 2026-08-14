"""The respond-send-user direct webhook on a HUMAN ticket-drawer send.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-J1 (a drawer send - text, attachment or template - calls the
            respond-send-user direct webhook: single-element array,
            source "User", the sender's REAL Respond user id,
            crm.business_id = the tracking id)
     AC-J2 (no other send path calls it - the CRM never sends bot traffic,
            and the shared chat-panel send must stay silent)
     AC-J3 (a sender with no mapped Respond user id: the send still
            succeeds and the webhook is SKIPPED, never sent with a CRM
            users.id UUID as the Respond user id)
     AC-J6 (the call carries the X-CRM-Webhook-Secret shared-secret header;
            an unset secret degrades to "sent without the header + warning",
            never to a blocked send)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S4.1)

The webhook is asserted at its real seam - the ``n8n_crm_chat_outbound``
integration_log row that ``enqueue_crm_chat_outbound_webhook`` writes, which
carries the exact payload that would be POSTed. Only the background HTTP thread
is stubbed; the payload under assertion is the real one. No Respond.io call is
ever made.

Run:
    venv/bin/pytest tests/test_human_send_webhook.py -q
"""
from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.integration import IntegrationLog
from app.models.respond_template import RespondChannel, RespondMessageTemplate
from app.models.respond_workspace import RespondWorkspace
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import SystemSetting, User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
RESPOND_IO_ID = "10025531"
SENDER_RESPOND_ID = "900001"
WEBHOOK_URL = "https://n8n.test/webhook/respond-send-user"
WEBHOOK_SECRET = "zzt-shared-secret"
SECRET_HEADER = "X-CRM-Webhook-Secret"
WORKSPACE_ID = str(uuid.uuid4())
CHANNEL_RID = 453209
# Respond message ids ARE epoch microseconds - use a real-shaped one so the
# mirror lanes can be deduped on it (AC-J5).
RESPOND_MESSAGE_ID = 1780751891000000


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _no_webhook_http():
    """The webhook POST runs on a daemon thread - stub the thread out entirely so
    the test asserts the payload, not the network."""
    with patch("app.services.crm_chat_outbound_webhook.threading"):
        yield


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    """AC-J6: the shared secret is configured for every test unless a test
    explicitly clears it."""
    from app.config import settings

    monkeypatch.setattr(settings, "n8n_crm_webhook_secret", WEBHOOK_SECRET, raising=False)
    monkeypatch.setenv("N8N_CRM_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _seed(db, *, sender_respond_user_id: str | None = SENDER_RESPOND_ID):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="ZZT-NORMAL", name="ZZT Normal"))
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
            respond_io_id=RESPOND_IO_ID,
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(
        User(
            id=assignee_id,
            email="zzt-cs1@test.com",
            name="Agent One",
            respond_user_id=sender_respond_user_id,
        )
    )
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="ZZT_CS_AGENT", name="ZZT CS Agent"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="ZZT Customer Service - Tier 1"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="zzt_cs_general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.add(
        SystemSetting(
            id=str(uuid.uuid4()),
            name="ZZT Sorento",
            n8n_crm_chat_outbound_webhook_url=WEBHOOK_URL,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "assignee_id": assignee_id,
        "agent_code": "ZZT_CS_AGENT",
        "team_set_code": "zzt_cs_general",
    }


def _create_ticket(db, seed, *, source_message_id="wamid.msg-1"):
    return ConversationSLATrackingService(db).create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id=source_message_id,
            source_message_text="Yes, please connect me to a person.",
        )
    )


def _seed_chat_default(db, use_case="conversation_chat"):
    db.add(
        RespondWorkspace(
            id=WORKSPACE_ID,
            space_id="364817",
            name="ZZT Sorento",
            api_key_ciphertext="not-encrypted-test",
            is_active=True,
            is_default=True,
        )
    )
    ch = RespondChannel(
        id=str(uuid.uuid4()), workspace_id=WORKSPACE_ID, respond_channel_id=CHANNEL_RID
    )
    db.add(ch)
    db.flush()
    tpl = RespondMessageTemplate(
        id=str(uuid.uuid4()),
        channel_id=ch.id,
        respond_template_id=1,
        name="chat_reply",
        language_code="en",
        status="approved",
        components=[{"type": "body", "text": "Message from {{1}}: {{2}}"}],
        body_text="Message from {{1}}: {{2}}",
        param_count=2,
    )
    db.add(tpl)
    db.commit()
    from app.services import respond_template_service as tsvc

    tsvc.set_default(
        db,
        use_case,
        template_id=str(tpl.id),
        param_mapping={"1": "sender_name", "2": "message"},
    )
    return tpl


class _FakeClient:
    def __init__(self, response=None):
        self.response = response if response is not None else {"messageId": RESPOND_MESSAGE_ID}
        self.send_message_calls = []

    def send_message(self, identifier, text):
        self.send_message_calls.append((identifier, text))
        return self.response


class _FakeTemplateClient:
    def __init__(self):
        self.calls = []

    def send_template_message(self, identifier, **kwargs):
        self.calls.append((identifier, kwargs))
        return {"messageId": RESPOND_MESSAGE_ID}


def _open_window(*_a, **_k):
    return {"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"}


def _webhook_logs(db):
    return (
        db.query(IntegrationLog)
        .filter(IntegrationLog.integration_channel == "n8n_crm_chat_outbound")
        .order_by(IntegrationLog.created_at.asc())
        .all()
    )


def _webhook_payloads(db):
    return [json.loads(row.request_payload) for row in _webhook_logs(db)]


def _webhook_headers(db):
    return [
        json.loads(row.request_headers) if row.request_headers else {}
        for row in _webhook_logs(db)
    ]


def _template_message_endpoint():
    from app.api.v1 import _respond_chat_template_routes as routes_module

    router = routes_module.build_chat_template_router(
        business_table="conversation_sla_tracking",
        resolver=lambda _db, _eid: (RESPOND_IO_ID, None),
        chat_use_case="conversation_chat",
    )
    return routes_module, next(
        r.endpoint
        for r in router.routes
        if getattr(r, "path", "") == "/{entity_id}/conversation/template-message"
    )


# --------------------------------------------------------------------------- #
# AC-J1 - a drawer text send fires the webhook exactly once                    #
# --------------------------------------------------------------------------- #


def test_drawer_text_send_fires_the_respond_send_user_webhook_once(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=_FakeClient()):
        service.send_ticket_message(
            str(t1.id),
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    payloads = _webhook_payloads(db)
    assert len(payloads) == 1, "one drawer send is one human-intervention signal"
    body = payloads[0]
    assert isinstance(body, list) and len(body) == 1, "the webhook body is a single-element array"
    envelope = body[0]
    assert envelope["source"] == "User"
    assert envelope["user"]["id"] == int(SENDER_RESPOND_ID), (
        "n8n evaluates user.id.toString() - it must be the sender's real Respond user id"
    )
    assert envelope["crm"]["business_table"] == "conversation_sla_tracking"
    assert envelope["crm"]["business_id"] == str(t1.id)
    assert envelope["message"]["messageId"] == RESPOND_MESSAGE_ID, (
        "the mirror lanes dedupe on the Respond messageId (AC-J5)"
    )
    assert envelope["message"]["message"]["text"] == "hello there"
    assert _webhook_headers(db)[0][SECRET_HEADER] == WEBHOOK_SECRET, (
        "AC-J6: the n8n branch gates on the shared secret, fail-closed"
    )


def test_drawer_attachment_send_fires_the_webhook_once(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        lambda **k: {"url": "https://cdn.test/a.pdf", "kind": "file"},
    ), patch(
        "app.services.integration_service.RespondClient"
    ) as client_cls:
        client_cls.for_identifier.return_value.send_attachment.return_value = {
            "messageId": RESPOND_MESSAGE_ID
        }
        result = service.send_ticket_message(
            str(t1.id),
            text="",
            files=[(b"pdf-bytes", "a.pdf", "application/pdf")],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["attachments"]["delivered"] == ["a.pdf"]
    payloads = _webhook_payloads(db)
    assert len(payloads) == 1
    assert payloads[0][0]["crm"]["business_id"] == str(t1.id)
    assert payloads[0][0]["source"] == "User"


def test_a_send_that_delivered_nothing_never_fires_the_webhook(db):
    """The lone attachment fails: nothing reached the contact, so there is no
    human reply to signal."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        lambda **k: {"url": "https://cdn.test/a.pdf", "kind": "file"},
    ), patch(
        "app.services.integration_service.RespondClient"
    ) as client_cls:
        client_cls.for_identifier.return_value.send_attachment.side_effect = RuntimeError(
            "Respond 502"
        )
        result = service.send_ticket_message(
            str(t1.id),
            text="",
            files=[(b"pdf-bytes", "a.pdf", "application/pdf")],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["attachments"]["failed"]["filename"] == "a.pdf"
    assert _webhook_payloads(db) == []


# --------------------------------------------------------------------------- #
# AC-J1 - the synchronous template send from the drawer fires it too           #
# --------------------------------------------------------------------------- #


def test_drawer_template_send_fires_the_webhook_once(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed)
    tpl = _seed_chat_default(db)
    routes_module, endpoint = _template_message_endpoint()

    with patch(
        "app.services.integration_service.RespondClient", return_value=_FakeTemplateClient()
    ):
        result = endpoint(
            str(t1.id),
            routes_module.TemplateMessageSendRequest(
                template_id=str(tpl.id),
                params={"1": "Agent One", "2": "hello there"},
                tracking_id=str(t1.id),
            ),
            db=db,
            current_user={"id": seed["assignee_id"], "name": "Agent One"},
        )

    assert result["queued"] is False
    payloads = _webhook_payloads(db)
    assert len(payloads) == 1
    envelope = payloads[0][0]
    assert envelope["source"] == "User"
    assert envelope["user"]["id"] == int(SENDER_RESPOND_ID)
    assert envelope["crm"]["business_table"] == "conversation_sla_tracking"
    assert envelope["crm"]["business_id"] == str(t1.id)


# --------------------------------------------------------------------------- #
# AC-J3 - no mapped Respond user id: send succeeds, webhook skipped            #
# --------------------------------------------------------------------------- #


def test_sender_without_a_mapped_respond_user_id_skips_the_webhook(db, caplog):
    seed = _seed(db, sender_respond_user_id=None)
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with caplog.at_level(logging.WARNING), patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=_FakeClient()):
        result = service.send_ticket_message(
            str(t1.id),
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["sent_as"] == "text", "the message still reaches the contact"
    assert _webhook_payloads(db) == [], (
        "a null/fake user.id throws inside n8n - skip instead"
    )
    assert any(
        "respond user id" in record.getMessage().lower() for record in caplog.records
    ), "the skip must be visible in the log, not silent"


def test_the_webhook_never_carries_a_crm_users_id_uuid(db):
    """A CRM users.id in respond_user_id is not a Respond id - it must not leak."""
    seed = _seed(db, sender_respond_user_id=str(uuid.uuid4()))
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=_FakeClient()):
        service.send_ticket_message(
            str(t1.id),
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert _webhook_payloads(db) == []


# --------------------------------------------------------------------------- #
# Best-effort post-commit: a webhook failure never fails a delivered send      #
# --------------------------------------------------------------------------- #


def test_a_webhook_failure_leaves_the_send_successful_and_the_outbox_intact(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    def _boom(*_a, **_k):
        raise RuntimeError("n8n unreachable")

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.integration_service.RespondClient", return_value=_FakeClient()
    ), patch(
        "app.services.crm_chat_outbound_webhook.enqueue_crm_chat_outbound_webhook", _boom
    ):
        result = service.send_ticket_message(
            str(t1.id),
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["sent_as"] == "text"
    outbox = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.integration_channel == "respond_io",
            IntegrationLog.business_id == str(t1.id),
        )
        .all()
    )
    assert len(outbox) == 1 and outbox[0].status == "success", (
        "the Respond outbox row survives a webhook failure (AC-D3)"
    )
    db.refresh(t1)
    assert t1.is_responded is True


# --------------------------------------------------------------------------- #
# AC-J6 - shared-secret header, and what an unset secret degrades to           #
# --------------------------------------------------------------------------- #


def _send_text(db, seed, tracking_id):
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=_FakeClient()):
        return ConversationSLATrackingService(db).send_ticket_message(
            tracking_id,
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )


def test_every_webhook_caller_carries_the_shared_secret_header(db):
    """Uniform emission: the PR-notification callers of the same enqueue path
    gain the header too, so n8n can eventually gate the whole webhook."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed)

    from app.services.crm_chat_outbound_webhook import enqueue_crm_chat_outbound_webhook

    enqueue_crm_chat_outbound_webhook(
        db,
        business_table="purchase_requests",
        business_id=str(t1.id),
        contact_respond_io_id=RESPOND_IO_ID,
        message_text="Your purchase request was approved.",
        respond_api_response={"messageId": RESPOND_MESSAGE_ID},
        space_id=None,
        crm_sender_user_id=seed["assignee_id"],
        respond_user_id_fallback=SENDER_RESPOND_ID,
    )

    assert _webhook_headers(db) == [{SECRET_HEADER: WEBHOOK_SECRET}]


def test_an_unset_secret_still_sends_the_webhook_and_warns(db, monkeypatch, caplog):
    """A misconfigured deploy degrades to bot-pause inert (the n8n gate stays
    closed), never to a blocked or failed send."""
    from app.config import settings

    monkeypatch.setattr(settings, "n8n_crm_webhook_secret", None, raising=False)
    monkeypatch.delenv("N8N_CRM_WEBHOOK_SECRET", raising=False)

    seed = _seed(db)
    t1 = _create_ticket(db, seed)

    with caplog.at_level(logging.WARNING):
        result = _send_text(db, seed, str(t1.id))

    assert result["sent_as"] == "text"
    assert len(_webhook_payloads(db)) == 1, "the webhook still goes out"
    assert _webhook_headers(db)[0].get(SECRET_HEADER) is None
    assert any(
        "N8N_CRM_WEBHOOK_SECRET" in record.getMessage() for record in caplog.records
    ), "an unset secret must be visible in the log"


# --------------------------------------------------------------------------- #
# AC-J2 - no other send path fires it                                          #
# --------------------------------------------------------------------------- #


class _NoCloseSession:
    def __init__(self, inner):
        self._inner = inner

    def close(self):  # noqa: D401 - deliberate no-op
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_the_shared_chat_panel_send_never_fires_the_webhook(db, monkeypatch):
    """complaint / stock-inquiry / purchase-request panels ride the same
    smart-send. Only the ticket drawer signals human intervention."""
    _seed(db)
    import app.database as database_module

    monkeypatch.setattr(database_module, "SessionLocal", lambda: _NoCloseSession(db))

    from app.tasks.respond_io_tasks import deliver_chat_message

    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=_FakeClient()):
        deliver_chat_message(
            RESPOND_IO_ID,
            None,
            "an ordinary complaint panel reply",
            "complaint_chat",
            "complaints",
            str(uuid.uuid4()),
            "Agent One",
            None,
        )

    assert _webhook_payloads(db) == []
