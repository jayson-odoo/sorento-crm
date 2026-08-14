"""Send-for-approval must tell the contact - and must survive Respond.io failing.

Every other transition on a PR/SF talks to the contact (approve, reject, processed,
closed). Pending-approval was the one silent step, so from the contact's side the form
went quiet between submitting and hearing a decision. These pin the fix:

  1. the transition into pending sends exactly one contact message;
  2. a redundant call (double-click / retry) does NOT re-send it;
  3. a Respond.io failure never rolls back the committed status.

Postgres only, `blank_session()` scratch schema.
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _seed_request(db, *, approval_status=None):
    from app.models.procurement import PurchaseRequestHeader

    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_number=f"ZZT-{uuid.uuid4().hex[:6]}",
        request_type="purchase_request",
        status="submitted",
        approval_status=approval_status,
    )
    db.add(header)
    db.commit()
    return header


def _service(db, monkeypatch, sends: list):
    """A PurchaseRequestService whose contact send is captured, not performed."""
    from app.services.procurement_service import PurchaseRequestService

    service = PurchaseRequestService(db)
    monkeypatch.setattr(
        service,
        "_send_purchase_request_contact_message",
        lambda header, **kwargs: sends.append(kwargs),
    )
    # URL builders touch settings / tokens irrelevant here.
    monkeypatch.setattr(
        service, "_purchase_request_portal_or_view_url", lambda *_a, **_k: "https://x/p"
    )
    monkeypatch.setattr(service, "_build_request_view_url", lambda *_a, **_k: "https://x/v")
    return service


def test_transition_into_pending_notifies_the_contact_once(db, monkeypatch):
    sends: list = []
    service = _service(db, monkeypatch, sends)
    header = _seed_request(db)

    service.set_pending_approval(str(header.id))

    assert len(sends) == 1
    text = sends[0]["message_text"]
    assert "sent for approval" in text
    assert header.request_number in text
    assert sends[0]["extra_context_vars"]["update"] == "Pending approval"


def test_redundant_call_does_not_resend(db, monkeypatch):
    """already_pending guard: a double-click or proxy retry must not re-message the
    contact (nor re-emit the SLA event - same guard)."""
    sends: list = []
    service = _service(db, monkeypatch, sends)
    header = _seed_request(db, approval_status="pending")

    service.set_pending_approval(str(header.id))

    assert sends == []


def test_send_failure_never_rolls_back_the_status(db, monkeypatch):
    """Best-effort: the status is committed before the send runs, and a Respond.io
    blow-up must surface as a warning, not a 500 for a transition that succeeded."""
    from app.services.procurement_service import PurchaseRequestService

    service = PurchaseRequestService(db)
    monkeypatch.setattr(
        service,
        "_notify_contact_on_pending_approval",
        lambda header: (_ for _ in ()).throw(RuntimeError("respond.io down")),
    )
    header = _seed_request(db)

    result = service.set_pending_approval(str(header.id))

    assert result.approval_status == "pending"
    db.refresh(header)
    assert header.approval_status == "pending"
