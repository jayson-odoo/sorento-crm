"""Respond.io WhatsApp template sync + 24h-window-aware sending
(PLAN-whatsapp-template-fallback):

- sync_templates: upsert by natural key, hard-delete rows gone from the API,
  idempotent re-run, body_text/param_count derivation, only-approved usable
- set/clear default: approval gate, full-param-mapping gate, variable
  validation, stale-key trimming, is_valid + template_removed flags
- get_window_state: open (recent incoming) vs closed (old / none),
  Respond-API-error -> chat_history fallback -> none -> closed, 23h margin
- sanitize_param: newlines -> " | ", whitespace collapse, truncation
- send_text_or_template: open -> plain text; closed -> default template;
  closed + no valid default -> TemplateSendSkipped

Run with:
    pytest tests/test_respond_templates.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.chat_history import ChatHistory
from app.models.lookup import LookupBinding
from app.models.respond_template import (
    RespondChannel,
    RespondMessageTemplate,
    RespondTemplateDefault,
)
from app.models.respond_workspace import RespondWorkspace

WORKSPACE_ID = str(uuid.uuid4())
CHANNEL_RID = 453209


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON

    for model in (RespondContact, RespondChannel, RespondMessageTemplate, RespondTemplateDefault, ChatHistory):
        for col in list(model.__table__.columns):
            if isinstance(col.type, JSONB):
                col.type = GenericJSON()
                col.server_default = None

    Base.metadata.create_all(
        engine,
        tables=[
            RespondWorkspace.__table__,
            RespondContact.__table__,
            RespondChannel.__table__,
            RespondMessageTemplate.__table__,
            RespondTemplateDefault.__table__,
            ChatHistory.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def workspace(db):
    ws = RespondWorkspace(
        id=WORKSPACE_ID,
        space_id="364817",
        name="Sorento",
        api_key_ciphertext="not-encrypted-test",
        is_active=True,
        is_default=True,
    )
    db.add(ws)
    db.commit()
    return ws


def _api_template(rid, name, status="approved", body="Hi {{1}}, update: {{2}}", params=2):
    return {
        "id": rid,
        "name": name,
        "languageCode": "en",
        "category": "UTILITY",
        "status": status,
        "statusDetail": None,
        "templateId": f"meta-{rid}",
        "namespace": None,
        "components": [{"type": "body", "text": body}],
    }


def _mock_client(channels, templates_by_channel):
    client = MagicMock()
    client.list_channels.return_value = channels
    client.list_message_templates.side_effect = lambda cid: templates_by_channel.get(int(cid), [])
    return client


# --------------------------------------------------------------------------- sync


def test_sync_inserts_channels_and_templates(db, workspace):
    from app.services import respond_template_service as svc

    client = _mock_client(
        [{"id": CHANNEL_RID, "name": "WA", "source": "whatsapp_business"}],
        {CHANNEL_RID: [_api_template(1, "update"), _api_template(2, "promo", status="rejected")]},
    )
    with patch.object(svc, "_client_for_workspace", return_value=client):
        result = svc.sync_templates(db)

    assert result == {"synced": 2, "deleted": 0, "channels": 1}
    rows = db.query(RespondMessageTemplate).all()
    assert {r.name for r in rows} == {"update", "promo"}
    upd = next(r for r in rows if r.name == "update")
    assert upd.param_count == 2
    assert upd.body_text.startswith("Hi {{1}}")


def test_sync_is_idempotent_and_hard_deletes_gone_rows(db, workspace):
    from app.services import respond_template_service as svc

    client = _mock_client(
        [{"id": CHANNEL_RID, "name": "WA", "source": "whatsapp_business"}],
        {CHANNEL_RID: [_api_template(1, "update"), _api_template(2, "promo")]},
    )
    with patch.object(svc, "_client_for_workspace", return_value=client):
        svc.sync_templates(db)
        # second run unchanged -> still 2 rows, none duplicated
        svc.sync_templates(db)
    assert db.query(RespondMessageTemplate).count() == 2

    # template 2 disappears from the API -> hard-deleted
    client2 = _mock_client(
        [{"id": CHANNEL_RID, "name": "WA", "source": "whatsapp_business"}],
        {CHANNEL_RID: [_api_template(1, "update")]},
    )
    with patch.object(svc, "_client_for_workspace", return_value=client2):
        result = svc.sync_templates(db)
    assert result["deleted"] == 1
    assert {r.name for r in db.query(RespondMessageTemplate).all()} == {"update"}


# --------------------------------------------------------------------------- defaults


def _seed_channel_with_template(db, *, name="update", status="approved", param_count=2):
    ch = RespondChannel(id=str(uuid.uuid4()), workspace_id=WORKSPACE_ID, respond_channel_id=CHANNEL_RID)
    db.add(ch)
    db.flush()
    tpl = RespondMessageTemplate(
        id=str(uuid.uuid4()),
        channel_id=ch.id,
        respond_template_id=1,
        name=name,
        language_code="en",
        status=status,
        components=[{"type": "body", "text": "Hi {{1}}, {{2}}"}],
        body_text="Hi {{1}}, {{2}}",
        param_count=param_count,
    )
    db.add(tpl)
    db.commit()
    return ch, tpl


def test_set_default_requires_full_param_mapping(db, workspace):
    from app.services import respond_template_service as svc
    from app.services.error_handler import AppException

    _, tpl = _seed_channel_with_template(db)
    with pytest.raises(AppException):
        svc.set_default(db, "complaint", template_id=str(tpl.id), param_mapping={"1": "contact_name"})


def test_set_default_rejects_unapproved_template(db, workspace):
    from app.services import respond_template_service as svc
    from app.services.error_handler import AppException

    _, tpl = _seed_channel_with_template(db, status="rejected")
    with pytest.raises(AppException):
        svc.set_default(
            db, "complaint", template_id=str(tpl.id),
            param_mapping={"1": "contact_name", "2": "message"},
        )


def test_set_default_rejects_unknown_variable(db, workspace):
    from app.services import respond_template_service as svc
    from app.services.error_handler import AppException

    _, tpl = _seed_channel_with_template(db)
    with pytest.raises(AppException):
        svc.set_default(
            db, "complaint", template_id=str(tpl.id),
            param_mapping={"1": "contact_name", "2": "bogus_var"},
        )


def test_set_default_portal_otp_requires_otp_code(db, workspace):
    # OTP template that covers every slot but never maps the code → rejected,
    # else a misconfigured OTP would ship a login message with no code.
    from app.services import respond_template_service as svc
    from app.services.error_handler import AppException

    _, tpl = _seed_channel_with_template(db)
    with pytest.raises(AppException):
        svc.set_default(
            db, "portal_otp", template_id=str(tpl.id),
            param_mapping={"1": "contact_name", "2": "message"},
        )


def test_set_default_portal_otp_accepts_when_code_mapped(db, workspace):
    from app.services import respond_template_service as svc

    _, tpl = _seed_channel_with_template(db)
    out = svc.set_default(
        db, "portal_otp", template_id=str(tpl.id),
        param_mapping={"1": "otp_code", "2": "message"},
    )
    assert out["is_valid"] is True
    assert "otp_code" in out["param_mapping"].values()


def test_set_default_happy_path_and_is_valid(db, workspace):
    from app.services import respond_template_service as svc

    _, tpl = _seed_channel_with_template(db)
    out = svc.set_default(
        db, "complaint", template_id=str(tpl.id),
        param_mapping={"1": "contact_name", "2": "message", "3": "status"},  # stale key trimmed
    )
    assert out["is_valid"] is True
    assert out["param_mapping"] == {"1": "contact_name", "2": "message"}


def test_default_flags_template_removed_after_sync_delete(db, workspace):
    from app.services import respond_template_service as svc

    _, tpl = _seed_channel_with_template(db)
    svc.set_default(
        db, "complaint", template_id=str(tpl.id),
        param_mapping={"1": "contact_name", "2": "message"},
    )
    # Simulate sync hard-deleting the template (FK SET NULL keeps the default row).
    db.query(RespondTemplateDefault).filter_by(use_case="complaint").update(
        {"template_id": None}
    )
    db.commit()
    row = svc.get_default_row(db, "complaint")
    serialized = svc.serialize_default("complaint", row)
    assert serialized["is_valid"] is False
    assert serialized["template_removed"] is True
    assert serialized["template_name"] == "update"  # snapshot survives


# --------------------------------------------------------------------------- window


def test_window_open_for_recent_incoming(db):
    from app.services import respond_messaging_service as svc

    recent_ms = int((datetime.utcnow() - timedelta(hours=2)).timestamp() * 1000)
    client = MagicMock()
    client.list_messages.return_value = {
        "items": [{"traffic": "incoming", "status": [{"timestamp": recent_ms}]}]
    }
    with patch("app.services.integration_service.RespondClient", return_value=client):
        state = svc.get_window_state(db, "id:123")
    assert state["open"] is True


def test_window_closed_for_old_incoming(db):
    from app.services import respond_messaging_service as svc

    old_ms = int((datetime.utcnow() - timedelta(hours=30)).timestamp() * 1000)
    client = MagicMock()
    client.list_messages.return_value = {
        "items": [{"traffic": "incoming", "status": [{"timestamp": old_ms}]}]
    }
    with patch("app.services.integration_service.RespondClient", return_value=client):
        state = svc.get_window_state(db, "id:123")
    assert state["open"] is False


def test_window_closed_when_no_incoming(db):
    from app.services import respond_messaging_service as svc

    client = MagicMock()
    client.list_messages.return_value = {"items": [{"traffic": "outgoing", "status": []}]}
    with patch("app.services.integration_service.RespondClient", return_value=client):
        state = svc.get_window_state(db, "id:123")
    assert state["open"] is False
    assert state["last_incoming_at"] is None


def test_window_falls_back_to_chat_history_on_api_error(db):
    from app.services import respond_messaging_service as svc

    contact_id = str(uuid.uuid4())
    db.add(
        ChatHistory(
            id=1,
            channel="whatsapp",
            contact_id=contact_id,
            phone_number="+60123",
            message="hi",
            sent_at=datetime.utcnow() - timedelta(hours=1),
            type="incoming",
        )
    )
    db.commit()

    client = MagicMock()
    client.list_messages.side_effect = RuntimeError("boom")
    with patch("app.services.integration_service.RespondClient", return_value=client):
        state = svc.get_window_state(db, "id:123", respond_contact_id=contact_id)
    assert state["open"] is True
    assert state["source"] == "chat_history"


# --------------------------------------------------------------------------- sanitize


def test_sanitize_param_flattens_newlines_and_collapses_space():
    from app.services.respond_messaging_service import sanitize_param

    out = sanitize_param("Status: approved\nReason:   damaged\n\nPortal: x")
    assert "\n" not in out
    assert " | " in out
    assert "   " not in out


def test_sanitize_param_truncates():
    from app.services.respond_messaging_service import sanitize_param

    out = sanitize_param("a" * 2000, max_len=50)
    assert len(out) == 50
    assert out.endswith("…")


def test_sanitize_param_empty_is_dash():
    from app.services.respond_messaging_service import sanitize_param

    assert sanitize_param("") == "-"
    assert sanitize_param(None) == "-"


# --------------------------------------------------------------------------- branch


def test_send_text_when_window_open(db):
    from app.services import respond_messaging_service as svc

    client = MagicMock()
    client.send_message.return_value = {"messageId": 1}
    with patch("app.services.integration_service.RespondClient", return_value=client), patch.object(
        svc, "get_window_state", return_value={"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"}
    ):
        result = svc.send_text_or_template(
            db, identifier="id:1", text="hello", use_case="complaint"
        )
    assert result["sent_as"] == "text"
    client.send_message.assert_called_once()


def test_send_template_when_window_closed(db, workspace):
    from app.services import respond_messaging_service as svc
    from app.services import respond_template_service as tsvc

    _, tpl = _seed_channel_with_template(db)
    tsvc.set_default(
        db, "complaint", template_id=str(tpl.id),
        param_mapping={"1": "contact_name", "2": "message"},
    )

    client = MagicMock()
    client.send_template_message.return_value = {"messageId": 9}
    with patch("app.services.integration_service.RespondClient", return_value=client), patch.object(
        svc, "get_window_state", return_value={"open": False, "last_incoming_at": None, "checked_at": "", "source": "x"}
    ):
        result = svc.send_text_or_template(
            db, identifier="id:1", text="Your complaint is approved",
            use_case="complaint", context_vars={"contact_name": "Ms Ang"},
        )
    assert result["sent_as"] == "template"
    client.send_template_message.assert_called_once()
    kwargs = client.send_template_message.call_args.kwargs
    assert kwargs["channel_id"] == CHANNEL_RID
    # message var defaults to the composed text
    assert "Your complaint is approved" in kwargs["parameters"][1]


def test_closed_window_without_default_raises_skipped(db, workspace):
    from app.services import respond_messaging_service as svc

    client = MagicMock()
    with patch("app.services.integration_service.RespondClient", return_value=client), patch.object(
        svc, "get_window_state", return_value={"open": False, "last_incoming_at": None, "checked_at": "", "source": "x"}
    ):
        with pytest.raises(svc.TemplateSendSkipped):
            svc.send_text_or_template(
                db, identifier="id:1", text="hello", use_case="complaint"
            )


# --------------------------------------------------------------------------- rbac


def test_template_permissions_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {e["slug"] for e in PERMISSION_REGISTRY}
    assert {
        "integration.respond_templates.view",
        "integration.respond_templates.edit",
        "integration.respond_templates.sync",
    } <= slugs


def test_send_template_message_payload_shape():
    """The send payload matches what the live Respond.io API accepts
    (verified 2026-06-08): channelId + message.type=whatsapp_template +
    template.components[body].text + positional parameters."""
    from app.services.integration_service import RespondClient

    captured = {}

    class _Resp:
        content = b"{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    with patch("app.services.integration_service.httpx.Client", return_value=_Client()), patch.object(
        RespondClient, "__init__", lambda self: setattr(self, "base_url", "https://api.respond.io") or setattr(self, "api_key", "k") or setattr(self, "space_id", None)
    ):
        RespondClient().send_template_message(
            "id:1",
            channel_id=CHANNEL_RID,
            template_name="update",
            language_code="en",
            body_text="Hi {{1}}, {{2}}",
            parameters=["Ms Ang", "approved"],
        )

    payload = captured["json"]
    assert payload["channelId"] == CHANNEL_RID
    assert payload["message"]["type"] == "whatsapp_template"
    tpl = payload["message"]["template"]
    assert tpl["name"] == "update"
    assert tpl["languageCode"] == "en"
    body = tpl["components"][0]
    assert body["type"] == "body"
    assert body["text"] == "Hi {{1}}, {{2}}"
    assert [p["text"] for p in body["parameters"]] == ["Ms Ang", "approved"]
