"""Rejecting a stock inquiry must not depend on the contact notification.

Both reject paths used to call `_send_stock_inquiry_contact_message(...)` BEFORE
mutating status and committing. A contact with no reachable Respond.io inbox —
e.g. a `respond_contacts` row missing `respond_io_id`, which leaves
`respond_inbox_url` NULL on every form created for that contact — makes that
send raise. The exception propagated out of the service, the route turned it
into a 400, and the inquiry stayed pending. The form could never be rejected at
all: the user got an error, retried, and hit the same wall every time.

`submit_inquiry_for_project_sales` and `project_sales_approve_inquiry` already
had the right shape — commit first, then notify best-effort. These tests pin
that the two reject paths now match, so the messaging side effect can fail
without taking the business action down with it.

Run: pytest tests/test_stock_inquiry_reject_notify_isolation.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.procurement import StockInquiry
from app.models.user import User
from app.services.procurement_service import StockInquiryService

SEND = "_send_stock_inquiry_contact_message"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON

    for col in list(RespondContact.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()
            col.server_default = None

    Base.metadata.create_all(
        engine,
        tables=[RespondContact.__table__, User.__table__, StockInquiry.__table__],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _inquiry(db, status: str) -> str:
    """A stock inquiry whose contact has no reachable inbox (the failing case)."""
    sid = str(uuid.uuid4())
    db.add(
        StockInquiry(
            id=sid,
            status=status,
            inquiry_number="SI26-TEST",
            respond_inbox_url=None,
        )
    )
    db.commit()
    return sid


def _svc(db) -> StockInquiryService:
    return StockInquiryService(db)


@pytest.mark.parametrize(
    "method,start_status",
    [
        ("project_sales_reject_inquiry", "pending_project_sales"),
        ("purchasing_reject_inquiry", "pending_purchasing"),
    ],
)
def test_reject_succeeds_when_contact_notification_raises(db, method, start_status):
    """The whole point: a failing send must not block the rejection."""
    sid = _inquiry(db, start_status)
    svc = _svc(db)

    with patch.object(
        svc,
        SEND,
        side_effect=RuntimeError(
            "respond_inbox_url is missing or invalid; cannot send message."
        ),
    ) as send, patch.object(svc, "_build_stock_inquiry_view_url", return_value="http://v/x"), \
            patch.object(svc, "_stock_inquiry_portal_or_view_url", return_value="http://p/x"):
        getattr(svc, method)(sid, reason="no stock", user_id=None)

    assert send.called, "expected the notification to still be attempted"

    row = db.query(StockInquiry).filter(StockInquiry.id == sid).first()
    assert row.status == "rejected", (
        f"{method} left status={row.status!r}; a failing contact notification must "
        "not roll back or skip the rejection itself."
    )
    assert row.rejection_reason == "no stock"
    assert row.rejected_at is not None
    assert row.rejected_from == start_status


@pytest.mark.parametrize(
    "method,start_status",
    [
        ("project_sales_reject_inquiry", "pending_project_sales"),
        ("purchasing_reject_inquiry", "pending_purchasing"),
    ],
)
def test_reject_is_committed_before_the_notification_runs(db, method, start_status):
    """Ordering, not just error-swallowing.

    Catching the exception around a send that still ran first would keep the row
    un-persisted at send time. Assert the committed state is already 'rejected'
    when the notification fires, which is what makes the send safe to fail.
    """
    sid = _inquiry(db, start_status)
    svc = _svc(db)
    seen = {}

    def _capture(*_a, **_k):
        # Record the FIRST send only. Recording the last would let an extra
        # pre-commit send slip through unnoticed as long as some later send
        # happened to run after the commit.
        if "status" in seen:
            return
        # Read through a fresh identity map so this reflects committed state.
        db.expire_all()
        seen["status"] = db.query(StockInquiry).filter(StockInquiry.id == sid).first().status

    with patch.object(svc, SEND, side_effect=_capture), \
            patch.object(svc, "_build_stock_inquiry_view_url", return_value="http://v/x"), \
            patch.object(svc, "_stock_inquiry_portal_or_view_url", return_value="http://p/x"):
        getattr(svc, method)(sid, reason="no stock", user_id=None)

    assert seen.get("status") == "rejected", (
        f"{method} notified while status was {seen.get('status')!r}; the commit must "
        "happen first so the send is a post-commit side effect."
    )
