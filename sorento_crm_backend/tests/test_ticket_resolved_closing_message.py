"""One closing WhatsApp message per resolved conversation ticket
(PLAN-ticket-resolved-closing-message, UAC sections A and B).

The CRM owns the message on every resolve lane; n8n keeps only the contact-level
housekeeping on the last open ticket. These tests pin the trigger (what enqueues,
what does not) and the job body (what is sent, logged and mirrored).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.chat_history import ChatHistory
from app.models.integration import IntegrationLog
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate, ConversationSLATrackingUpdate
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
RESPOND_IO_ID = "10025531"
MSG_US = 1_787_640_441_538_436
ENQUIRY = "My wardrobe door hinge is loose, can someone advise?"


@pytest.fixture
def enqueued(monkeypatch):
    """Every RQ enqueue, captured instead of queued."""
    import app.services.queue_service as queue_service

    calls: list[dict] = []

    def _capture(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})
        return None

    monkeypatch.setattr(queue_service, "enqueue_job", _capture)
    return calls


@pytest.fixture
def db(enqueued):
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    # The close-convo webhook spawns a daemon thread; never in a test.
    with patch("app.services.crm_close_convo_webhook.threading"):
        yield


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


def _create_ticket(db, seed, *, source_message_id="wamid.msg-1", text_=ENQUIRY):
    return ConversationSLATrackingService(db).create_tracking(
        ConversationSLATrackingCreate(
            agent_code="CS_AGENT",
            team_set_code="cs_general",
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id=source_message_id,
            source_message_text=text_,
        )
    )


def _resolve(db, tracking_id, *, origin="user"):
    return ConversationSLATrackingService(db).update_tracking(
        str(tracking_id), ConversationSLATrackingUpdate(is_resolved=True), resolve_origin=origin
    )


def _closing_jobs(enqueued):
    from app.tasks.respond_io_tasks import send_ticket_resolved_message

    return [c for c in enqueued if c["func"] is send_ticket_resolved_message]


# --------------------------------------------------------------------------- #
# A. Trigger                                                                  #
# --------------------------------------------------------------------------- #


def test_a_user_resolve_enqueues_one_closing_message_for_that_ticket(db, enqueued):
    seed = _seed(db)
    t = _create_ticket(db, seed)
    _resolve(db, t.id)

    jobs = _closing_jobs(enqueued)
    assert len(jobs) == 1
    assert jobs[0]["args"] == (str(t.id),)
    assert jobs[0]["kwargs"].get("queue_name") == "respond_io"


def test_an_api_key_resolve_enqueues_it_too(db, enqueued):
    """n8n's Respond-app-close lane resolves each open ticket by API key; the CRM
    is the only sender now, so that lane must not go quiet (AC-A2)."""
    seed = _seed(db)
    t = _create_ticket(db, seed)
    _resolve(db, t.id, origin="api_key")
    assert len(_closing_jobs(enqueued)) == 1


def test_each_of_several_open_tickets_gets_its_own_message_when_resolved(db, enqueued):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.a")
    t2 = _create_ticket(db, seed, source_message_id="wamid.b", text_="Second enquiry")

    _resolve(db, t1.id)
    assert [j["args"] for j in _closing_jobs(enqueued)] == [(str(t1.id),)]

    _resolve(db, t2.id)
    assert [j["args"] for j in _closing_jobs(enqueued)] == [(str(t1.id),), (str(t2.id),)]


def test_a_form_sla_stage_row_sends_nothing(db, enqueued):
    seed = _seed(db)
    t = _create_ticket(db, seed)
    t.source_entity_type = "complaint"
    t.source_entity_id = str(uuid.uuid4())
    db.commit()

    _resolve(db, t.id)
    assert _closing_jobs(enqueued) == []


def test_re_resolving_an_already_resolved_ticket_sends_nothing(db, enqueued):
    seed = _seed(db)
    t = _create_ticket(db, seed)
    _resolve(db, t.id)
    assert len(_closing_jobs(enqueued)) == 1

    _resolve(db, t.id)
    assert len(_closing_jobs(enqueued)) == 1


def test_a_queue_failure_never_fails_the_resolve(db, enqueued, monkeypatch):
    import app.services.queue_service as queue_service

    def _boom(func, *a, **k):
        from app.tasks.respond_io_tasks import send_ticket_resolved_message

        if func is send_ticket_resolved_message:
            raise RuntimeError("redis is away")
        return None

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)
    seed = _seed(db)
    t = _create_ticket(db, seed)

    resolved = _resolve(db, t.id)
    assert resolved.is_resolved is True


# --------------------------------------------------------------------------- #
# B. The job                                                                  #
# --------------------------------------------------------------------------- #


class _NoCloseSession:
    def __init__(self, inner):
        self._inner = inner

    def close(self):  # noqa: D401 - the test owns the session
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture
def worker_db(db, monkeypatch):
    import app.database as database_module

    monkeypatch.setattr(database_module, "SessionLocal", lambda: _NoCloseSession(db))
    return db


def _fake_send_factory(calls: list[dict]):
    def _fake_send(db_, *, identifier, text, use_case, context_vars=None, respond_contact_id=None):
        calls.append(
            {
                "identifier": identifier,
                "text": text,
                "use_case": use_case,
                "context_vars": dict(context_vars or {}),
            }
        )
        return {
            "sent_as": "text",
            "response": {"messageId": MSG_US},
            "window_state": {"open": True},
            "request_payload": {"message": {"type": "text", "text": text}},
            "rendered_text": text,
        }

    return _fake_send


def test_the_job_sends_the_closing_text_with_the_contact_and_enquiry_vars(worker_db, enqueued):
    from app.tasks.respond_io_tasks import send_ticket_resolved_message

    db = worker_db
    seed = _seed(db)
    t = _create_ticket(db, seed)
    sends: list[dict] = []
    with patch(
        "app.services.respond_messaging_service.send_text_or_template", _fake_send_factory(sends)
    ):
        result = send_ticket_resolved_message(str(t.id))

    assert result["status"] == "success"
    assert len(sends) == 1
    send = sends[0]
    assert send["use_case"] == "ticket_resolved"
    assert send["identifier"] == RESPOND_IO_ID
    assert send["context_vars"]["contact_name"] == "Aisyah Rahman"
    assert send["context_vars"]["message"] == ENQUIRY
    assert send["text"] == (
        f'Hi Aisyah Rahman, your enquiry "{ENQUIRY}" has been resolved. '
        "If there is anything else we can help with, just reply here."
    )

    # AC-B4: the Respond outbox row, against the ticket.
    logs = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.integration_channel == "respond_io",
            IntegrationLog.business_table == "conversation_sla_tracking",
            IntegrationLog.business_id == str(t.id),
        )
        .all()
    )
    assert [log.status for log in logs] == ["success"]

    # AC-B5: the thread sees it at once.
    rows = db.query(ChatHistory).filter(ChatHistory.contact_id == RESPOND_IO_ID).all()
    assert [(r.type, r.message, r.message_id) for r in rows] == [
        ("outgoing", send["text"], str(MSG_US))
    ]


def test_a_ticket_without_an_enquiry_text_says_so_without_an_empty_quote(worker_db, enqueued):
    from app.tasks.respond_io_tasks import send_ticket_resolved_message

    db = worker_db
    seed = _seed(db)
    t = _create_ticket(db, seed, text_="")
    sends: list[dict] = []
    with patch(
        "app.services.respond_messaging_service.send_text_or_template", _fake_send_factory(sends)
    ):
        send_ticket_resolved_message(str(t.id))

    assert sends[0]["context_vars"]["message"] == "your enquiry"
    assert sends[0]["text"] == (
        "Hi Aisyah Rahman, your enquiry has been resolved. "
        "If there is anything else we can help with, just reply here."
    )


def test_a_long_enquiry_is_excerpted_for_the_message(worker_db, enqueued):
    from app.tasks.respond_io_tasks import send_ticket_resolved_message

    db = worker_db
    seed = _seed(db)
    long_text = "x" * 300
    t = _create_ticket(db, seed, text_=long_text)
    sends: list[dict] = []
    with patch(
        "app.services.respond_messaging_service.send_text_or_template", _fake_send_factory(sends)
    ):
        send_ticket_resolved_message(str(t.id))

    excerpt = sends[0]["context_vars"]["message"]
    assert len(excerpt) == 120
    assert excerpt.endswith("...")


def test_a_contact_without_a_respond_id_is_skipped(worker_db, enqueued):
    from app.tasks.respond_io_tasks import send_ticket_resolved_message

    db = worker_db
    seed = _seed(db)
    t = _create_ticket(db, seed)
    contact = db.query(RespondContact).filter(RespondContact.id == seed["contact_id"]).one()
    contact.respond_io_id = None
    db.commit()
    sends: list[dict] = []
    with patch(
        "app.services.respond_messaging_service.send_text_or_template", _fake_send_factory(sends)
    ):
        result = send_ticket_resolved_message(str(t.id))

    assert result["status"] == "skipped"
    assert sends == []


def test_the_use_case_is_offered_to_admins():
    from app.models.respond_template import TEMPLATE_DEFAULT_USE_CASES

    assert "ticket_resolved" in TEMPLATE_DEFAULT_USE_CASES
