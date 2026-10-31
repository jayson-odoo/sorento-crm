"""Portal OTP and portal link sends go out through the contact's OWN workspace.

Follow-up to #2028 (portal contact resolved within its workspace). Resolving the
right contact is not enough: the Respond.io client that carries the OTP or the
link must be the one for that contact's workspace, not the default workspace's.
A contact in a non-default workspace otherwise gets its code through the wrong
workspace, or not at all.

Twin contacts share a Respond.io id across two workspaces, so a send keyed on the
bare identifier cannot tell them apart: the send must be keyed on the contact row.

No network: every Respond.io call is replaced on the client class and records the
API key of the client that made it.
"""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.complaints import Complaint  # noqa: F401  (model registry)
from app.models.integration import IntegrationLog
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services import integration_service
from app.services import respond_messaging_service
from app.services.portal_service import PortalService, _hash_otp, _utcnow
from app.utils.field_encryption import encrypt_secret


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup(db):
    state = {"contacts": [], "workspaces": [], "otps": []}
    yield state
    db.rollback()
    if state["otps"]:
        db.query(IntegrationLog).filter(IntegrationLog.business_id.in_(state["otps"])).delete(
            synchronize_session=False
        )
    if state["contacts"]:
        tokens = [
            t.id
            for t in db.query(PortalToken).filter(PortalToken.contact_id.in_(state["contacts"]))
        ]
        if tokens:
            db.query(IntegrationLog).filter(IntegrationLog.business_id.in_(tokens)).delete(
                synchronize_session=False
            )
        db.query(PortalToken).filter(PortalToken.contact_id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
        db.query(PortalOtpCode).filter(PortalOtpCode.contact_id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
        db.query(RespondContact).filter(RespondContact.id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
    if state["workspaces"]:
        db.query(RespondWorkspace).filter(RespondWorkspace.id.in_(state["workspaces"])).delete(
            synchronize_session=False
        )
    db.commit()


def _workspace(db, cleanup, key: str) -> RespondWorkspace:
    w = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="Test WS",
        api_key_ciphertext=encrypt_secret(key),
        base_url="https://respond.invalid",
    )
    db.add(w)
    db.flush()
    cleanup["workspaces"].append(w.id)
    return w


def _contact(db, cleanup, *, respond_io_id: str, workspace_id) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="Tester",
        respond_io_id=respond_io_id,
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


@pytest.fixture
def twins(db, cleanup):
    """Two non-default workspaces, each holding a contact with the SAME Respond.io id.

    Contact ``b`` is created FIRST so that a lookup on the bare identifier, which
    takes whichever row comes back, is not accidentally right for ``a``.
    """
    rid = f"9{uuid.uuid4().int % 10**9:09d}"
    key_a = f"key-a-{uuid.uuid4().hex[:8]}"
    key_b = f"key-b-{uuid.uuid4().hex[:8]}"
    ws_a = _workspace(db, cleanup, key_a)
    ws_b = _workspace(db, cleanup, key_b)
    b = _contact(db, cleanup, respond_io_id=rid, workspace_id=ws_b.id)
    db.commit()
    a = _contact(db, cleanup, respond_io_id=rid, workspace_id=ws_a.id)
    db.commit()
    return SimpleNamespace(rid=rid, ws_a=ws_a, ws_b=ws_b, a=a, b=b, key_a=key_a, key_b=key_b)


@pytest.fixture
def respond_calls(monkeypatch):
    """Replace every Respond.io call with a recorder of the calling client's key.

    ``window_open`` decides what the window check sees: an incoming message a
    minute ago (open, free-text send) or nothing (closed, template send).
    """
    calls = {"list": [], "send": [], "template": [], "window_open": True}

    def _list_messages(self, identifier, limit=50, cursor=None):
        calls["list"].append(self.api_key)
        if not calls["window_open"]:
            return {"items": []}
        # Respond.io encodes an incoming message's time in messageId (epoch us).
        return {"items": [{"traffic": "incoming", "status": [], "messageId": int(time.time() * 1e6)}]}

    def _send_message(self, identifier, text, *a, **k):
        calls["send"].append(self.api_key)
        return {"messageId": 1}

    def _send_template_message(self, identifier, **k):
        calls["template"].append(self.api_key)
        return {"messageId": 2}

    monkeypatch.setattr(integration_service.RespondClient, "list_messages", _list_messages)
    monkeypatch.setattr(integration_service.RespondClient, "send_message", _send_message)
    monkeypatch.setattr(
        integration_service.RespondClient, "send_template_message", _send_template_message
    )
    respond_messaging_service.reset_window_cache()
    yield calls
    respond_messaging_service.reset_window_cache()


def _otp_row(db, cleanup, contact, space_id) -> PortalOtpCode:
    otp = PortalOtpCode(
        contact_id=contact.id,
        space_id=space_id,
        code_hash=_hash_otp("123456"),
        expires_at=_utcnow(),
    )
    db.add(otp)
    db.commit()
    db.refresh(otp)
    cleanup["otps"].append(otp.id)
    return otp


@pytest.mark.parametrize("task_name", ["send_portal_otp_respond_message", "send_login_otp_respond_message"])
def test_otp_send_uses_contact_workspace_client(db, cleanup, twins, respond_calls, task_name):
    from app.tasks import respond_io_tasks

    otp = _otp_row(db, cleanup, twins.a, twins.ws_a.space_id)
    task = getattr(respond_io_tasks, task_name)
    task(otp.id, twins.rid, "code 123456", "123456", twins.ws_a.space_id)

    assert respond_calls["send"] == [twins.key_a]
    # The window is read from the same workspace the message goes through.
    assert respond_calls["list"] == [twins.key_a]


def test_otp_template_send_uses_contact_workspace_client(
    db, cleanup, twins, respond_calls, monkeypatch
):
    """Closed window: the template goes through the contact's workspace too."""
    from app.tasks import respond_io_tasks

    respond_calls["window_open"] = False
    template = SimpleNamespace(
        name="portal_otp",
        id=uuid.uuid4(),
        language_code="en",
        body_text="Your code is {{1}}",
        channel=SimpleNamespace(respond_channel_id=1),
    )
    monkeypatch.setattr(
        respond_messaging_service,
        "build_template_request",
        lambda db, use_case, context_vars: {
            "template": template,
            "params": ["123456"],
            "button": None,
            "request_payload": {"message": {"type": "whatsapp_template"}},
        },
    )
    otp = _otp_row(db, cleanup, twins.a, twins.ws_a.space_id)
    respond_io_tasks.send_portal_otp_respond_message(
        otp.id, twins.rid, "code 123456", "123456", twins.ws_a.space_id
    )

    assert respond_calls["template"] == [twins.key_a]
    assert respond_calls["send"] == []


def test_portal_link_send_uses_contact_workspace_client(db, twins, respond_calls):
    PortalService(db).send_link_via_respond_io(
        twins.rid, twins.ws_a.space_id, "https://portal.example"
    )
    assert respond_calls["send"] == [twins.key_a]


def test_submission_link_resolves_respond_id_in_named_workspace(db, twins):
    """A row storing the Respond.io id resolves to the contact in the row's workspace."""
    svc = PortalService(db)
    link_a = svc.submission_link(
        twins.rid, "complaint", "e1", base_url="https://p.example", space_id=twins.ws_a.space_id
    )
    link_b = svc.submission_link(
        twins.rid, "complaint", "e1", base_url="https://p.example", space_id=twins.ws_b.space_id
    )
    db.refresh(twins.a)
    db.refresh(twins.b)
    assert link_a == f"https://p.example/portal/c/{twins.a.portal_slug}/complaint/e1"
    assert link_b == f"https://p.example/portal/c/{twins.b.portal_slug}/complaint/e1"


def test_complaint_status_link_passes_row_space_id(db, twins, monkeypatch):
    """The complaint status message link carries the complaint's workspace."""
    from app.services.complaints_service import ComplaintService

    seen = {}

    def _spy(self, contact_id, submission_type, entity_id=None, base_url=None, space_id=None):
        seen["space_id"] = space_id
        return "https://p.example/x"

    monkeypatch.setattr(PortalService, "submission_link", _spy)
    svc = ComplaintService.__new__(ComplaintService)
    svc.db = db
    monkeypatch.setattr(svc, "_complaint_public_view_links_enabled", lambda: True, raising=False)
    complaint = SimpleNamespace(contact_id=twins.rid, space_id=twins.ws_a.space_id)
    svc._complaint_status_link_part(complaint, "e1")
    assert seen["space_id"] == twins.ws_a.space_id


@pytest.mark.parametrize(
    "cls_name,method",
    [
        ("StockInquiryService", "_stock_inquiry_portal_or_view_url"),
        ("PurchaseRequestService", "_purchase_request_portal_or_view_url"),
    ],
)
def test_procurement_portal_links_pass_row_space_id(db, twins, monkeypatch, cls_name, method):
    from app.services import procurement_service

    seen = {}

    def _spy(self, contact_id, submission_type, entity_id=None, base_url=None, space_id=None):
        seen["space_id"] = space_id
        return "https://p.example/x"

    monkeypatch.setattr(PortalService, "submission_link", _spy)
    cls = getattr(procurement_service, cls_name)
    svc = cls.__new__(cls)
    svc.db = db
    row = SimpleNamespace(contact_id=twins.rid, space_id=twins.ws_b.space_id, request_type=None)
    getattr(svc, method)(row, "e1")
    assert seen["space_id"] == twins.ws_b.space_id
