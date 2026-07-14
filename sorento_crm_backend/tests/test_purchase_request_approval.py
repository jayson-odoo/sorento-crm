"""Purchase-request approval advances the lifecycle status.

Bug: after an approve/reject decision via the public approval link the request
still displayed "Submitted" because only ``approval_status`` was written; the
lifecycle ``status`` stayed "submitted". Both must move.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.procurement import (
    ApprovalToken,
    PurchaseRequestHeader,
    PurchaseRequestLine,
)
from app.models.user import User
from app.services import procurement_service as procurement_service_mod
from app.services.procurement_service import PurchaseRequestService


@pytest.fixture(autouse=True)
def _silence_side_effects(monkeypatch):
    """Approval fires Respond.io / requester notifications + automation dispatch;
    none are relevant to the status transition. No-op them."""
    for name in (
        "_notify_requester_on_approved",
        "_notify_contact_on_approval_approved",
        "_notify_contact_on_approval_rejected",
        "_dispatch_approval_automation",
    ):
        monkeypatch.setattr(
            procurement_service_mod.PurchaseRequestService, name, lambda self, *a, **kw: None
        )
    monkeypatch.setattr(
        procurement_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            PurchaseRequestHeader.__table__,
            PurchaseRequestLine.__table__,
            ApprovalToken.__table__,
            User.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_submitted_request_with_token(db) -> str:
    header_id = str(uuid.uuid4())
    db.add(
        PurchaseRequestHeader(
            id=header_id,
            request_type="purchase_request",
            status="submitted",
            approval_status=None,
        )
    )
    token = f"tok-{uuid.uuid4()}"
    db.add(
        ApprovalToken(
            id=str(uuid.uuid4()),
            entity_type="purchase_request",
            entity_id=header_id,
            token=token,
            expires=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24),
        )
    )
    db.commit()
    return token


@pytest.mark.parametrize("action", ["approved", "rejected"])
def test_submit_approval_advances_status(db, action):
    token = _seed_submitted_request_with_token(db)
    service = PurchaseRequestService(db)

    header = service.submit_approval(
        token, action, approved_by="approver@example.com", approval_comments="ok"
    )

    assert header.approval_status == action
    assert header.status == action
    assert header.status != "submitted"


def test_reject_submitted_advances_status(db):
    header_id = str(uuid.uuid4())
    db.add(
        PurchaseRequestHeader(
            id=header_id,
            request_type="purchase_request",
            status="submitted",
            approval_status=None,
        )
    )
    db.commit()
    service = PurchaseRequestService(db)

    header = service.reject_submitted(header_id, "not needed", actor_user_id="u1")

    assert header.approval_status == "rejected"
    assert header.status == "rejected"


def test_reject_submitted_stores_actor_name_not_uuid(db):
    """`approved_by` (the "Rejected by" field) must hold a display name, never a raw UUID."""
    actor_id = str(uuid.uuid4())
    db.add(User(id=actor_id, name="CK Lee", email="ck@example.com"))
    header_id = str(uuid.uuid4())
    db.add(
        PurchaseRequestHeader(
            id=header_id,
            request_type="purchase_request",
            status="submitted",
            approval_status=None,
        )
    )
    db.commit()
    service = PurchaseRequestService(db)

    header = service.reject_submitted(header_id, "not needed", actor_user_id=actor_id)

    assert header.approved_by == "CK Lee"  # resolved name, not the UUID
    assert header.approved_by != actor_id
    # Raw actor id is preserved separately for FK / audit purposes.
    assert header.requested_approval_by_user_id == actor_id


def test_reject_submitted_unmatched_uuid_not_leaked(db):
    """An actor UUID with no matching user row must not leak into `approved_by`."""
    orphan_id = str(uuid.uuid4())
    header_id = str(uuid.uuid4())
    db.add(
        PurchaseRequestHeader(
            id=header_id,
            request_type="purchase_request",
            status="submitted",
            approval_status=None,
        )
    )
    db.commit()
    service = PurchaseRequestService(db)

    header = service.reject_submitted(header_id, "not needed", actor_user_id=orphan_id)

    assert header.approved_by == ""  # UUID-shaped + no user -> blank, never the UUID
