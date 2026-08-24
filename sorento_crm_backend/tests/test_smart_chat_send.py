"""Smart chat send (PLAN-unified-conversation-composer-smart-send, UAC-20).

Covers:
- ``respond_chat_template_service.send_chat_message_for``: in-window plain text vs
  out-of-window ``*_chat`` template, ``no_chat_template`` 422, sanitize/flatten flag,
  raw-text-to-send in-window, outbox written on SUCCESS and FAILURE, best-effort log.
- ``build_chat_template_router`` POST ``/{entity_id}/conversation/send-message``:
  auth denial, empty-text 422 validation, resolver-no-identifier validation,
  sender_name derivation, happy path.
- ``respond_template_service.set_default`` chat-template ``message`` enforcement.
- ``get_defaults`` exposes the 5 new chat use cases.

Run: venv/bin/pytest tests/test_smart_chat_send.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.integration import IntegrationLog
from app.models.respond_template import (
    RespondChannel,
    RespondMessageTemplate,
)
from app.models.respond_workspace import RespondWorkspace
from tests._pg_fixture import blank_session

WORKSPACE_ID = str(uuid.uuid4())
CHANNEL_RID = 453209


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed_chat_default(db, use_case="complaint_chat", *, mapping=None):
    """Seed an approved 2-param template + a valid ``*_chat`` default."""
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
        param_mapping=mapping or {"1": "sender_name", "2": "message"},
    )
    return tpl


class _FakeTemplateSend:
    """Stand-in for send_template_for_use_case - captures kwargs, canned result."""

    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls = []

    def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


def _template_result(params=("Jay", "Ms Ang", "hi there")):
    """Shape returned by the real send_template_for_use_case (subset used here)."""
    return {
        "response": {"id": "m-template"},
        "template_name": "chat_reply",
        "template_id": "tpl-1",
        "params": list(params),
        "button": None,
        "request_payload": {"message": {"body_text": "Hi {{1}} from {{2}}: {{3}}"}},
    }


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


# --------------------------------------------------------------- service: branches


def test_window_open_sends_plain_text(db):
    from app.services import respond_chat_template_service as svc

    client = _FakeClient()
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.integration_service.RespondClient", return_value=client
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="hello there friend",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "text"
    assert out["rendered_text"] == "hello there friend"
    assert out["flattened"] is False
    # RAW typed text delivered verbatim via send_message; template path untouched.
    assert client.send_message_calls == [("id:60123", "hello there friend")]
    assert tmpl.calls == []


def test_window_closed_sends_template_with_sanitized_message(db):
    from app.services import respond_chat_template_service as svc

    _seed_chat_default(db)
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="hi\nthere",  # newline -> flattened to a space for the param
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "template"
    # rendered_text = render_filled_body(body_text, params).
    assert out["rendered_text"] == "Hi Jay from Ms Ang: hi there"
    # The message context var carries the SANITIZED (flattened) text.
    assert tmpl.calls[0]["context_vars"]["message"] == "hi there"
    assert tmpl.calls[0]["context_vars"]["sender_name"] == "Jay"


def test_window_closed_without_default_raises_no_chat_template(db):
    from app.services import respond_chat_template_service as svc
    from app.services.error_handler import AppException

    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ):
        with pytest.raises(AppException) as ei:
            svc.send_chat_message_for(
                db,
                identifier="id:60123",
                text="hi",
                chat_use_case="complaint_chat",
                business_table="complaints",
                business_id=str(uuid.uuid4()),
                sender_name="Jay",
            )
    exc = ei.value
    assert exc.status_code == 422
    assert exc.detail["code"] == "no_chat_template"
    assert exc.detail["detail"] == "/integration-management/whatsapp-templates"


# --------------------------------------------------------------- service: sanitize


def test_in_window_multiline_not_flattened_and_raw_delivered(db):
    """In-window multiline: never flattened; the RAW multiline text is delivered."""
    from app.services import respond_chat_template_service as svc

    raw = "Hello\n\nthere\tfriend    x"
    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text=raw,
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "text"
    assert out["flattened"] is False
    assert out["rendered_text"] == raw.strip()
    # RAW multiline text forwarded verbatim (formatting preserved).
    assert client.send_message_calls == [("id:60123", raw)]


def test_out_of_window_multiline_is_flattened(db):
    """Out-of-window multiline: sanitized into the param -> flattened True."""
    from app.services import respond_chat_template_service as svc

    _seed_chat_default(db)
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="Hello\n\nthere\tfriend    x",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "template"
    assert out["flattened"] is True
    # message param carries the SANITIZED text (no newlines/tabs/space-runs).
    assert tmpl.calls[0]["context_vars"]["message"] == "Hello there friend x"


def test_single_line_not_flattened_in_either_window(db):
    from app.services import respond_chat_template_service as svc

    # In-window single line -> flattened False.
    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        out_open = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="just one line",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out_open["flattened"] is False

    # Closed-window single line -> also flattened False (sanitize is a no-op).
    _seed_chat_default(db)
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        out_closed = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="just one line",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out_closed["flattened"] is False


def test_in_window_delivers_raw_text_even_when_chat_template_configured(db):
    """Regression: in-window must deliver the RAW multiline text verbatim, NOT the
    rendered template body - even when a valid *_chat default IS configured. This is
    the exact bug the fix addressed (the old choke point rendered the body in-window)."""
    from app.services import respond_chat_template_service as svc

    _seed_chat_default(db)  # a VALID no-button complaint_chat default exists
    raw = "Line one\nLine two\nRegards, Jay"
    client = _FakeClient()
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.integration_service.RespondClient", return_value=client
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text=raw,
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "text"
    assert out["flattened"] is False
    # Contact received the RAW multiline text - the template body was NOT rendered.
    assert client.send_message_calls == [("id:60123", raw)]
    assert tmpl.calls == []


# --------------------------------------------------------------- service: outbox


def test_outbox_written_on_success_for_text_and_template(db):
    from app.services import respond_chat_template_service as svc

    # In-window text send -> a success outbox row.
    text_bid = str(uuid.uuid4())
    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="hi",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=text_bid,
            sender_name="Jay",
        )
    text_row = db.query(IntegrationLog).filter(IntegrationLog.business_id == text_bid).first()
    assert text_row is not None
    assert text_row.status == "success"
    assert text_row.business_table == "complaints"
    assert str(text_row.business_id) == text_bid

    # Closed-window template send -> also a success outbox row.
    _seed_chat_default(db)
    tmpl_bid = str(uuid.uuid4())
    tmpl = _FakeTemplateSend(result=_template_result())
    with patch(
        "app.services.respond_messaging_service.get_window_state", _closed_window
    ), patch(
        "app.services.respond_messaging_service.send_template_for_use_case", tmpl
    ):
        svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="hi",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=tmpl_bid,
            sender_name="Jay",
        )
    tmpl_row = db.query(IntegrationLog).filter(IntegrationLog.business_id == tmpl_bid).first()
    assert tmpl_row is not None
    assert tmpl_row.status == "success"


def test_outbox_written_on_failure_and_raises_502(db):
    from app.services import respond_chat_template_service as svc
    from app.services.error_handler import AppException

    business_id = str(uuid.uuid4())
    client = _FakeClient(raises=RuntimeError("respond 401"))
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch("app.services.integration_service.RespondClient", return_value=client):
        with pytest.raises(AppException) as ei:
            svc.send_chat_message_for(
                db,
                identifier="id:60123",
                text="hi",
                chat_use_case="complaint_chat",
                business_table="complaints",
                business_id=business_id,
                sender_name="Jay",
            )
    assert ei.value.status_code == 502
    assert ei.value.detail["code"] == "respond_send_failed"
    row = db.query(IntegrationLog).filter(IntegrationLog.business_id == business_id).first()
    assert row is not None
    assert row.status == "failed"
    assert row.business_table == "complaints"


def test_success_returned_even_when_outbox_write_fails(db):
    """Best-effort: a failing success-log write must NOT mask a delivered send."""
    from app.services import respond_chat_template_service as svc
    from app.services.integration_service import IntegrationLogService

    client = _FakeClient()
    with patch(
        "app.services.respond_messaging_service.get_window_state", _open_window
    ), patch(
        "app.services.integration_service.RespondClient", return_value=client
    ), patch.object(
        IntegrationLogService,
        "create_integration_log",
        side_effect=RuntimeError("db down"),
    ):
        out = svc.send_chat_message_for(
            db,
            identifier="id:60123",
            text="hi",
            chat_use_case="complaint_chat",
            business_table="complaints",
            business_id=str(uuid.uuid4()),
            sender_name="Jay",
        )
    assert out["sent_as"] == "text"
    assert out["rendered_text"] == "hi"
    # The send itself happened even though the outbox write blew up.
    assert client.send_message_calls == [("id:60123", "hi")]


# --------------------------------------------------------------- set_default: chat


def test_set_default_chat_rejects_without_message_slot(db):
    from app.services import respond_template_service as tsvc
    from app.services.error_handler import AppException

    # Seed workspace + channel + approved template (2 params) but map neither to message.
    _seed_chat_default(db, mapping={"1": "sender_name", "2": "message"})
    # Re-fetch the template to build a fresh mapping without `message`.
    tpl = db.query(RespondMessageTemplate).first()
    with pytest.raises(AppException):
        tsvc.set_default(
            db,
            "complaint_chat",
            template_id=str(tpl.id),
            param_mapping={"1": "contact_name", "2": "sender_name"},
        )


def test_set_default_chat_succeeds_with_message_no_sender(db):
    from app.services import respond_template_service as tsvc

    _seed_chat_default(db, mapping={"1": "sender_name", "2": "message"})
    tpl = db.query(RespondMessageTemplate).first()
    out = tsvc.set_default(
        db,
        "complaint_chat",
        template_id=str(tpl.id),
        param_mapping={"1": "contact_name", "2": "message"},  # no sender_name -> allowed
    )
    assert out["is_valid"] is True
    assert "message" in out["param_mapping"].values()
    assert "sender_name" not in out["param_mapping"].values()


def test_get_defaults_includes_five_chat_use_cases(db):
    from app.services import respond_template_service as tsvc

    use_cases = {d["use_case"] for d in tsvc.get_defaults(db)}
    assert {
        "complaint_chat",
        "stock_inquiry_chat",
        "purchase_request_chat",
        "sponsorship_form_chat",
        "conversation_chat",
    } <= use_cases


# ------------------------------------------------ service: chat-template preview


def test_chat_template_preview_configured_returns_slots(db):
    """Valid no-button *_chat default with {"1":"sender_name","2":"message"}:
    slot 1 resolves the sender_name arg (read-only), slot 2 is the editable
    message field (value None)."""
    from app.services import respond_chat_template_service as svc

    _seed_chat_default(db, mapping={"1": "sender_name", "2": "message"})
    out = svc.get_chat_template_preview(
        db,
        identifier="id:60123",
        respond_contact_id=None,
        chat_use_case="complaint_chat",
        sender_name="Admin",
        entity_id=str(uuid.uuid4()),
    )
    assert out["configured"] is True
    assert out["template_name"] == "chat_reply"
    assert out["body_text"] == "Message from {{1}}: {{2}}"
    assert out["slots"]["1"] == {
        "variable": "sender_name",
        "value": "Admin",
        "editable": False,
    }
    assert out["slots"]["2"] == {
        "variable": "message",
        "value": None,
        "editable": True,
    }


def test_chat_template_preview_no_valid_default_returns_not_configured(db):
    """No configured/valid chat default -> {configured: False, settings_url}."""
    from app.services import respond_chat_template_service as svc

    out = svc.get_chat_template_preview(
        db,
        identifier="id:60123",
        respond_contact_id=None,
        chat_use_case="complaint_chat",
        sender_name="Admin",
        entity_id=str(uuid.uuid4()),
    )
    assert out == {
        "configured": False,
        "settings_url": "/integration-management/whatsapp-templates",
    }


def test_chat_template_preview_context_builder_failure_is_guarded(db):
    """A context_builder that raises must not break the preview - configured stays
    True and non-message slots depending on it resolve to "" instead of 500ing."""
    from app.services import respond_chat_template_service as svc

    # Map slot 1 to a variable supplied ONLY by the context_builder (portal_url),
    # so a builder failure leaves it unresolved ("") rather than crashing.
    _seed_chat_default(db, mapping={"1": "portal_url", "2": "message"})

    def _boom(_db, _entity_id):
        raise RuntimeError("context build failed")

    out = svc.get_chat_template_preview(
        db,
        identifier="id:60123",
        respond_contact_id=None,
        chat_use_case="complaint_chat",
        sender_name="Admin",
        entity_id=str(uuid.uuid4()),
        context_builder=_boom,
    )
    assert out["configured"] is True
    # The builder-dependent, non-message slot degrades to an empty resolved value.
    assert out["slots"]["1"] == {
        "variable": "portal_url",
        "value": "",
        "editable": False,
    }
    assert out["slots"]["2"]["editable"] is True
    assert out["slots"]["2"]["value"] is None


# --------------------------------------------------------------- route


def _make_app(db, resolver, *, user=None):
    from app.api.v1._respond_chat_template_routes import build_chat_template_router
    from app.database import get_db
    from app.dependencies import get_current_user

    router = build_chat_template_router(
        business_table="complaints",
        resolver=resolver,
        chat_use_case="complaint_chat",
    )
    app = FastAPI()
    app.include_router(router, prefix="/complaints")
    app.dependency_overrides[get_db] = lambda: db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


def _ok_resolver(_db, _entity_id):
    return ("id:60123", str(uuid.uuid4()))


def _no_id_resolver(_db, _entity_id):
    return (None, None)


def test_route_requires_authentication(db):
    # No get_current_user override -> the real dependency 401s on a missing token.
    app = _make_app(db, _ok_resolver)
    client = TestClient(app)
    resp = client.post("/complaints/c1/conversation/send-message", json={"text": "hi"})
    assert resp.status_code in (401, 403)


def test_route_empty_text_is_422(db):
    app = _make_app(db, _ok_resolver, user={"id": str(uuid.uuid4()), "name": "Jay"})
    client = TestClient(app)
    resp = client.post("/complaints/c1/conversation/send-message", json={"text": ""})
    assert resp.status_code == 422


def test_route_no_linked_contact_is_validation_error(db):
    app = _make_app(db, _no_id_resolver, user={"id": str(uuid.uuid4()), "name": "Jay"})
    client = TestClient(app)
    resp = client.post("/complaints/c1/conversation/send-message", json={"text": "hi"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == "VALIDATION_ERROR"


def test_route_happy_path_passes_sender_name_from_user(db):
    captured = {}

    def _fake_send(db_arg, **kwargs):
        captured.update(kwargs)
        return {
            "sent_as": "text",
            "rendered_text": "hi",
            "flattened": False,
            "window_state": {"open": True, "last_incoming_at": None},
        }

    app = _make_app(db, _ok_resolver, user={"id": str(uuid.uuid4()), "name": "Jay Tan"})
    client = TestClient(app)
    with patch(
        "app.services.respond_chat_template_service.send_chat_message_for", _fake_send
    ):
        resp = client.post(
            "/complaints/abc/conversation/send-message", json={"text": "hi"}
        )
    assert resp.status_code == 200
    assert resp.json()["sent_as"] == "text"
    assert captured["sender_name"] == "Jay Tan"
    assert captured["business_table"] == "complaints"
    assert captured["business_id"] == "abc"


def test_route_system_principal_falls_back_to_customer_service(db):
    captured = {}

    def _fake_send(db_arg, **kwargs):
        captured.update(kwargs)
        return {
            "sent_as": "text",
            "rendered_text": "hi",
            "flattened": False,
            "window_state": {"open": True, "last_incoming_at": None},
        }

    # A principal with no name (API-key/system) -> "Customer Service" fallback.
    app = _make_app(db, _ok_resolver, user={"id": str(uuid.uuid4()), "name": ""})
    client = TestClient(app)
    with patch(
        "app.services.respond_chat_template_service.send_chat_message_for", _fake_send
    ):
        resp = client.post(
            "/complaints/abc/conversation/send-message", json={"text": "hi"}
        )
    assert resp.status_code == 200
    assert captured["sender_name"] == "Customer Service"
