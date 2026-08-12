"""ConversationSLATrackingService.send_ticket_message / mark_ticket_responded /
is_ambiguous_fallback_response - S2c, previously ZERO coverage.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-E1 (per-ticket response clock, sibling untouched)
     AC-D2 (closed window -> template smart-send fallback, reused verbatim)
     AC-D3 (integration_log outbox on success AND failure, actually-attempted payload)
     AC-E3 (Respond-app-reply fallback ambiguity guard: 2+ open tickets for the
            same (contact, assignee) -> no clock change; exactly one -> unambiguous)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S2.5, S2.6)

RespondClient / the template-send machinery are monkeypatched throughout - no
real Respond.io HTTP call is ever made (mirrors tests/test_smart_chat_send.py).

Run:
    venv/bin/pytest tests/test_conversation_ticket_send.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.integration import IntegrationLog
from app.models.respond_template import RespondChannel, RespondMessageTemplate
from app.models.respond_workspace import RespondWorkspace
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.error_handler import AppException
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
WORKSPACE_ID = str(uuid.uuid4())
CHANNEL_RID = 453209


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    # No Redis in the unit harness - notify/enqueue side effects are best-effort
    # and swallow errors, but stub anyway so the test never depends on a broker.
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


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
    other_assignee_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    db.add(User(id=other_assignee_id, email="cs2@test.com", name="Agent Two", respond_user_id="900002"))
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
        "other_assignee_id": other_assignee_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _create_ticket(db, seed, *, source_message_id, assignee_id=None, **over):
    service = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=assignee_id or seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id=source_message_id,
        source_message_text="Yes, please connect me to a person.",
        **over,
    )
    return service.create_tracking(payload)


def _seed_chat_default(db, use_case="conversation_chat"):
    """Seed an approved 2-param template + a valid ``*_chat`` default (mirrors
    tests/test_smart_chat_send.py)."""
    ws = RespondWorkspace(
        id=WORKSPACE_ID,
        space_id="364817",
        name="Sorento",
        api_key_ciphertext="not-encrypted-test",
        is_active=True,
        is_default=True,
    )
    db.add(ws)
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
    """Stand-in for RespondClient - records send_message(identifier, text) calls."""

    def __init__(self, response=None, raises=None):
        self.response = response if response is not None else {"id": "m-text"}
        self.raises = raises
        self.send_message_calls = []

    def send_message(self, identifier, text):
        self.send_message_calls.append((identifier, text))
        if self.raises is not None:
            raise self.raises
        return self.response


def _open_window(*_a, **_k):
    return {"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"}


def _closed_window(*_a, **_k):
    return {"open": False, "last_incoming_at": None, "checked_at": "", "source": "x"}


class _FakeTemplateSend:
    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls = []

    def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


def _template_result(params=("Jay", "hi there")):
    return {
        "response": {"id": "m-template"},
        "template_name": "chat_reply",
        "template_id": "tpl-1",
        "params": list(params),
        "button": None,
        "request_payload": {"message": {"body_text": "Message from {{1}}: {{2}}"}},
    }


def _outbox_rows(db, tracking_id):
    return (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.business_table == "conversation_sla_tracking",
            IntegrationLog.business_id == str(tracking_id),
        )
        .order_by(IntegrationLog.created_at.asc())
        .all()
    )


# --------------------------------------------------------------------------- #
# AC-E1: send from T1's drawer stamps ONLY T1's response clock                 #
# --------------------------------------------------------------------------- #


def test_send_from_one_ticket_stamps_only_that_ticket(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
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
    assert client.send_message_calls == [("10025531", "hello there")]

    db.refresh(t1)
    db.refresh(t2)
    assert t1.is_responded is True
    assert t1.responded_at is not None
    assert t1.responded_by == seed["assignee_id"]
    assert t1.response_time is not None

    # Sibling ticket for the SAME contact must be completely untouched.
    assert t2.is_responded is False
    assert t2.responded_at is None
    assert t2.responded_by is None
    assert t2.response_time is None


def test_mark_ticket_responded_is_a_noop_on_a_second_call(db):
    """Only the FIRST reply stops the response clock (docstring contract)."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    service.mark_ticket_responded(t1, responded_by_user_id=seed["assignee_id"])
    db.refresh(t1)
    first_responded_at = t1.responded_at
    assert first_responded_at is not None

    # A second stamp attempt (e.g. a later ordinary reply) must not move the clock.
    service.mark_ticket_responded(t1, responded_by_user_id=seed["other_assignee_id"])
    db.refresh(t1)
    assert t1.responded_at == first_responded_at
    assert t1.responded_by == seed["assignee_id"], "responded_by must not change on the no-op path"


# --------------------------------------------------------------------------- #
# AC-D2: closed window -> template fallback fires (reused verbatim)           #
# --------------------------------------------------------------------------- #


def test_send_on_closed_window_falls_back_to_template(db):
    seed = _seed(db)
    _seed_chat_default(db, use_case="conversation_chat")
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        result = service.send_ticket_message(
            str(t1.id),
            text="hi there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["sent_as"] == "template"
    assert tmpl.calls, "template smart-send must have been invoked out-of-window"
    assert tmpl.calls[0]["context_vars"]["message"] == "hi there"

    db.refresh(t1)
    assert t1.is_responded is True, "a template-fallback send still stamps the response clock"


def test_send_on_closed_window_without_a_default_is_a_validation_error(db):
    """No *_chat default configured -> no_chat_template 422, matching the shared
    composer's contract (D2 reuses send_chat_message_for VERBATIM)."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    with patch("app.services.respond_messaging_service.get_window_state", _closed_window):
        with pytest.raises(AppException) as ei:
            service.send_ticket_message(
                str(t1.id),
                text="hi there",
                files=[],
                reply_to_message_id=None,
                reply_to_excerpt=None,
                sender_user_id=seed["assignee_id"],
                sender_name="Agent One",
            )
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "no_chat_template"

    db.refresh(t1)
    assert t1.is_responded is False


# --------------------------------------------------------------------------- #
# AC-D3: integration_log outbox on success AND failure                        #
# --------------------------------------------------------------------------- #


def test_outbox_written_on_success_with_actually_attempted_payload(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        service.send_ticket_message(
            str(t1.id),
            text="hello there",
            files=[],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    rows = _outbox_rows(db, t1.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.integration_channel == "respond_io"
    assert '"type": "text"' in row.request_payload
    assert '"hello there"' in row.request_payload


def test_outbox_written_on_a_mocked_respond_failure(db):
    """A Respond 4xx/5xx must still write a 'failed' outbox row with the payload
    that was actually attempted (text, not a fabricated default) - and the
    ticket's response clock must NOT be stamped for a send that never landed."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    client = _FakeClient(raises=RuntimeError("Respond 401 unauthorized"))
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        with pytest.raises(AppException) as ei:
            service.send_ticket_message(
                str(t1.id),
                text="hello there",
                files=[],
                reply_to_message_id=None,
                reply_to_excerpt=None,
                sender_user_id=seed["assignee_id"],
                sender_name="Agent One",
            )
    assert ei.value.status_code == 502
    assert ei.value.detail["code"] == "respond_send_failed"

    rows = _outbox_rows(db, t1.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failed"
    assert '"type": "text"' in row.request_payload
    assert '"hello there"' in row.request_payload

    db.refresh(t1)
    assert t1.is_responded is False, "a failed send must never stop the response clock"


# --------------------------------------------------------------------------- #
# AC-E3: Respond-app-reply fallback ambiguity guard                           #
# --------------------------------------------------------------------------- #


def test_two_open_tickets_same_assignee_is_ambiguous(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    assert service.is_ambiguous_fallback_response(t1) is True
    assert service.is_ambiguous_fallback_response(t2) is True


def test_exactly_one_open_ticket_is_unambiguous(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    # Resolve the sibling; the remaining ticket is now the ONLY open one for
    # this (contact, assignee) pair -> the fallback becomes unambiguous.
    t2.is_resolved = True
    db.commit()

    assert service.is_ambiguous_fallback_response(t1) is False


def test_different_assignees_are_never_ambiguous_with_each_other(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1", assignee_id=seed["assignee_id"])
    t2 = _create_ticket(
        db, seed, source_message_id="wamid.msg-2", assignee_id=seed["other_assignee_id"]
    )
    service = ConversationSLATrackingService(db)

    assert service.is_ambiguous_fallback_response(t1) is False
    assert service.is_ambiguous_fallback_response(t2) is False


def test_already_responded_ticket_is_never_ambiguous(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    t1.is_responded = True
    db.commit()

    assert service.is_ambiguous_fallback_response(t1) is False


def test_form_sla_rows_are_never_ambiguous(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t1.source_entity_type = "complaint"
    db.commit()
    _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    assert service.is_ambiguous_fallback_response(t1) is False


def test_no_contact_or_no_assignee_is_never_ambiguous(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    t1.respond_contact_id = None
    db.commit()
    assert service.is_ambiguous_fallback_response(t1) is False

    db.refresh(t1)
    t1.respond_contact_id = seed["contact_id"]
    t1.assigned_to_id = None
    db.commit()
    assert service.is_ambiguous_fallback_response(t1) is False


# --------------------------------------------------------------------------- #
# FINDING 2 (code review): the predicate above keyed on the resolved          #
# `tracking` argument's OWN assigned_to_id and counted ALL open siblings      #
# (is_resolved=False only) - wrong in both directions. The tests above still  #
# pass unchanged (they never exercise the new `responded_by` parameter, so    #
# they pin the fallback-to-the-tracking's-own-assignee default, which is      #
# unaffected), but they under-specified the contract: AC-E3 is about the      #
# (contact, REPLYING user) pair, not "this pre-resolved row's own assignee".  #
# These two pin the actual bugs the finding named.                           #
# --------------------------------------------------------------------------- #


def test_responded_by_param_finds_ambiguity_the_default_assignee_misses(db):
    """(a) False negative: the n8n Respond-app-reply fallback resolves a
    contact-level "preferred" tracking (t1, assigned to seed[assignee_id])
    separately from identifying WHO actually replied (payload's
    `responded_by`). The old code only ever asked "does t1's own assignee
    hold 2+ open tickets?" - t1's assignee holds exactly one, so it always
    answered False, even when the real replier (seed[other_assignee_id], who
    holds TWO) is a completely different user. Passing `responded_by`
    (resolved in update_tracking from the payload before this call) fixes it."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1", assignee_id=seed["assignee_id"])
    _create_ticket(db, seed, source_message_id="wamid.msg-2", assignee_id=seed["other_assignee_id"])
    _create_ticket(db, seed, source_message_id="wamid.msg-3", assignee_id=seed["other_assignee_id"])
    service = ConversationSLATrackingService(db)

    assert (
        service.is_ambiguous_fallback_response(t1, responded_by=seed["other_assignee_id"])
        is True
    ), "the ACTUAL replier holds 2 open unanswered tickets - ambiguous regardless of t1's own assignee"
    assert (
        service.is_ambiguous_fallback_response(t1, responded_by=seed["assignee_id"]) is False
    ), "seed[assignee_id] really does hold exactly one open ticket (t1 itself)"
    # No responded_by supplied at all -> unchanged default: falls back to the
    # tracking's own assignee (seed[assignee_id], one ticket -> unambiguous).
    assert service.is_ambiguous_fallback_response(t1) is False


def test_already_responded_sibling_never_inflates_ambiguity(db):
    """(b) False positive: the old query filtered only `is_resolved=False`,
    so an ALREADY-RESPONDED-but-not-yet-resolved sibling (still "open") was
    counted as a competing candidate even though it can no longer be the
    ticket a NEW reply is answering. A lone still-unanswered ticket must
    never be ambiguous."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    service = ConversationSLATrackingService(db)

    t2.is_responded = True
    db.commit()

    assert service.is_ambiguous_fallback_response(t1) is False


# --------------------------------------------------------------------------- #
# FINDING 3 (code review): multi-attachment sends re-resolved the window per  #
# file (each a live Respond HTTP call, 15s timeout), sent the caption only    #
# AFTER every attachment (never if one failed), raised 502 on the first       #
# per-file failure (leaving files 1..N-1 delivered with no way to tell the    #
# FE which ones), and skipped mark_ticket_responded on any exception even     #
# when something DID reach the contact.                                      #
# --------------------------------------------------------------------------- #


def _fake_upload_chat_attachment(*, business_table, business_id, content, filename, mime):
    return {"url": f"https://cdn.test/{filename}", "kind": "document"}


class _FakeAttachmentClient:
    """Stand-in for RespondClient.for_identifier(...) - records
    send_attachment(identifier, attachment_type, url) calls; can fail on a
    chosen filename (identified via the fake upload's filename-embedding url)."""

    def __init__(self, fail_on_filename=None, fail_error="Respond 500 unavailable"):
        self.calls = []
        self.fail_on_filename = fail_on_filename
        self.fail_error = fail_error

    def send_attachment(self, identifier, attachment_type, url):
        self.calls.append((identifier, attachment_type, url))
        if self.fail_on_filename and url.endswith(self.fail_on_filename):
            raise RuntimeError(self.fail_error)
        return {"id": f"m-attachment-{len(self.calls)}"}


def _respond_client_mock(*, text_client=None, attachment_client=None):
    """A fake RespondClient CLASS: RespondClient() (direct instantiation, used
    by the text/caption send path) returns text_client; RespondClient.for_identifier(...)
    (the attachment send path) returns attachment_client."""
    mock_cls = MagicMock(return_value=text_client or _FakeClient())
    mock_cls.for_identifier = MagicMock(return_value=attachment_client or _FakeAttachmentClient())
    return mock_cls


def _counting_window(counter, *, open_=True):
    def _inner(*_a, **_k):
        counter["n"] = counter.get("n", 0) + 1
        return {"open": open_, "last_incoming_at": None, "checked_at": "", "source": "x"}

    return _inner


def test_multi_attachment_send_resolves_the_window_exactly_once(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    counter: dict = {}
    attachment_client = _FakeAttachmentClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _counting_window(counter)
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(attachment_client=attachment_client),
    ):
        service.send_ticket_message(
            str(t1.id),
            text="",
            files=[
                (b"a", "a.pdf", "application/pdf"),
                (b"b", "b.pdf", "application/pdf"),
                (b"c", "c.pdf", "application/pdf"),
            ],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert counter["n"] == 1, "the window must be resolved ONCE for the whole send, not per file"
    assert len(attachment_client.calls) == 3


def test_caption_ships_even_when_a_later_attachment_fails(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    text_client = _FakeClient()
    attachment_client = _FakeAttachmentClient(fail_on_filename="b.pdf")
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(text_client=text_client, attachment_client=attachment_client),
    ):
        result = service.send_ticket_message(
            str(t1.id),
            text="see attached",
            files=[
                (b"a", "a.pdf", "application/pdf"),
                (b"b", "b.pdf", "application/pdf"),
                (b"c", "c.pdf", "application/pdf"),
            ],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert text_client.send_message_calls == [("10025531", "see attached")], (
        "the caption must ship even though file b.pdf failed - never dropped "
        "because of an unrelated attachment failure"
    )
    assert result["attachments"]["delivered"] == ["a.pdf"], "a.pdf was sent before b.pdf failed"
    assert result["attachments"]["failed"]["filename"] == "b.pdf"
    assert "Respond 500" in result["attachments"]["failed"]["error"]
    # c.pdf was never attempted - Respond delivers in order; nothing after the
    # first failure is attempted so a caller retrying doesn't resend a.pdf.
    assert len(attachment_client.calls) == 2

    db.refresh(t1)
    assert t1.is_responded is True, "a.pdf AND the caption reached the contact - must stamp"


def test_partial_attachment_failure_returns_a_structured_result_not_a_raise(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    attachment_client = _FakeAttachmentClient(fail_on_filename="only.pdf")
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(attachment_client=attachment_client),
    ):
        result = service.send_ticket_message(
            str(t1.id),
            text="",
            files=[(b"x", "only.pdf", "application/pdf")],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["sent_as"] == "attachment"
    assert result["attachments"]["delivered"] == []
    assert result["attachments"]["failed"]["filename"] == "only.pdf"

    db.refresh(t1)
    assert t1.is_responded is False, "nothing reached the contact - must not stamp"


def test_all_attachments_succeed_stamps_the_response_clock_and_reports_none_failed(db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    attachment_client = _FakeAttachmentClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.respond_chat_template_service.upload_chat_attachment",
        _fake_upload_chat_attachment,
    ), patch(
        "app.services.integration_service.RespondClient",
        _respond_client_mock(attachment_client=attachment_client),
    ):
        result = service.send_ticket_message(
            str(t1.id),
            text="",
            files=[(b"a", "a.pdf", "application/pdf"), (b"b", "b.pdf", "application/pdf")],
            reply_to_message_id=None,
            reply_to_excerpt=None,
            sender_user_id=seed["assignee_id"],
            sender_name="Agent One",
        )

    assert result["attachments"]["delivered"] == ["a.pdf", "b.pdf"]
    assert result["attachments"]["failed"] is None

    db.refresh(t1)
    assert t1.is_responded is True


# --------------------------------------------------------------------------- #
# FINDING 4 (code review): "Send template" from the ticket drawer posts to the #
# generic /{id}/conversation/template-message route, which never stamped the   #
# ticket - so an out-of-window template reply left the response clock running  #
# and the ticket breached while visibly answered. The route/body now carries   #
# an optional tracking_id and the worker stamps THAT ticket on success.        #
# --------------------------------------------------------------------------- #


class _NoCloseSession:
    """Delegates to the test session but ignores close(): the RQ task closes
    the session it believes it opened, while the fixture owns ours."""

    def __init__(self, inner):
        self._inner = inner

    def close(self):  # noqa: D401 - deliberate no-op
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _patch_session_local(monkeypatch, db):
    import app.database as database_module

    monkeypatch.setattr(database_module, "SessionLocal", lambda: _NoCloseSession(db))


def test_manual_template_send_stamps_only_the_named_ticket(db, monkeypatch):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")
    _patch_session_local(monkeypatch, db)
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.send_manual_template_for",
        lambda *a, **k: {"ok": True, "template_name": "conversation_follow_up"},
    )

    from app.tasks.respond_io_tasks import deliver_manual_template

    deliver_manual_template(
        "10025531",
        "tpl-1",
        {"1": "Agent One"},
        "conversation_sla_tracking",
        str(t1.id),
        seed["assignee_id"],
        str(t1.id),
    )

    db.refresh(t1)
    db.refresh(t2)
    assert t1.is_responded is True
    assert str(t1.responded_by) == seed["assignee_id"]
    assert t2.is_responded is False, "sibling ticket must be untouched (AC-E1)"


def test_manual_template_send_without_a_tracking_id_stamps_nothing(db, monkeypatch):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _patch_session_local(monkeypatch, db)
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.send_manual_template_for",
        lambda *a, **k: {"ok": True},
    )

    from app.tasks.respond_io_tasks import deliver_manual_template

    deliver_manual_template(
        "10025531", "tpl-1", {}, "complaints", str(uuid.uuid4()), seed["assignee_id"]
    )

    db.refresh(t1)
    assert t1.is_responded is False


def test_manual_template_send_that_fails_does_not_stamp(db, monkeypatch):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _patch_session_local(monkeypatch, db)

    def _boom(*_a, **_k):
        raise RuntimeError("Respond 401 unauthorized")

    monkeypatch.setattr(
        "app.services.respond_chat_template_service.send_manual_template_for", _boom
    )

    from app.tasks.respond_io_tasks import deliver_manual_template

    with pytest.raises(RuntimeError):
        deliver_manual_template(
            "10025531",
            "tpl-1",
            {},
            "conversation_sla_tracking",
            str(t1.id),
            seed["assignee_id"],
            str(t1.id),
        )

    db.refresh(t1)
    assert t1.is_responded is False


def test_manual_template_stamp_is_idempotent_and_skips_form_sla_rows(db, monkeypatch):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    service = ConversationSLATrackingService(db)

    # Already answered: the stamp is a no-op, the first response time stands.
    service.mark_ticket_responded(t1, responded_by_user_id=seed["assignee_id"])
    db.refresh(t1)
    first_responded_at = t1.responded_at
    service.mark_ticket_responded_by_id(
        str(t1.id), responded_by_user_id=seed["other_assignee_id"]
    )
    db.refresh(t1)
    assert t1.responded_at == first_responded_at
    assert str(t1.responded_by) == seed["assignee_id"]

    # A form-SLA stage row is a different family - never stamped from here.
    form_row = _create_ticket(db, seed, source_message_id="wamid.msg-form")
    form_row.source_entity_type = "complaint"
    db.commit()
    assert service.mark_ticket_responded_by_id(str(form_row.id)) is None
    db.refresh(form_row)
    assert form_row.is_responded is False

    # An unknown id is not an error: nothing to stamp.
    assert service.mark_ticket_responded_by_id(str(uuid.uuid4())) is None


def test_manual_template_stamp_refuses_a_ticket_belonging_to_another_contact(db, monkeypatch):
    """The worker only stamps a ticket whose contact actually received the
    template - the tracking id comes from the client, the identifier does not."""
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _patch_session_local(monkeypatch, db)
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.send_manual_template_for",
        lambda *a, **k: {"ok": True},
    )

    from app.tasks.respond_io_tasks import deliver_manual_template

    deliver_manual_template(
        "99999999",  # a different contact than the ticket's
        "tpl-1",
        {},
        "conversation_sla_tracking",
        str(t1.id),
        seed["assignee_id"],
        str(t1.id),
    )

    db.refresh(t1)
    assert t1.is_responded is False


def test_template_message_route_passes_tracking_id_to_the_worker(monkeypatch):
    """The route wiring: tracking_id on the body reaches deliver_manual_template."""
    from app.api.v1 import _respond_chat_template_routes as routes_module

    captured: dict = {}

    def _fake_enqueue(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        return MagicMock(id="job-1")

    monkeypatch.setattr(
        "app.services.queue_service.enqueue_job", _fake_enqueue
    )
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.precheck_manual_template",
        lambda *a, **k: {"template_name": "t", "rendered_body": "b"},
    )

    router = routes_module.build_chat_template_router(
        business_table="conversation_sla_tracking",
        resolver=lambda _db, _eid: ("10025531", "contact-1"),
    )
    endpoint = next(
        r.endpoint
        for r in router.routes
        if getattr(r, "path", "") == "/{entity_id}/conversation/template-message"
    )

    tracking_id = str(uuid.uuid4())
    endpoint(
        "entity-1",
        routes_module.TemplateMessageSendRequest(
            template_id="tpl-1", params={}, tracking_id=tracking_id
        ),
        db=MagicMock(),
        current_user={"id": "user-1", "name": "Agent One"},
    )

    assert captured["args"][-1] == tracking_id
