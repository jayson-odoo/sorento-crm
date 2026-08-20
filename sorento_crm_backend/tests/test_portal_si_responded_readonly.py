"""Portal: a `responded` stock inquiry is read-only on the plain-edit path.

Purchasing hitting respond (a clarifying question) used to leave the salesperson
free to edit-and-resubmit straight through draft/submit. That is reversed: a
`responded` inquiry can now only be changed through Revise
(``PortalRevisionService.revise``) - draft-save and plain submit both reject it,
mirroring how `rejected` blocks draft-save but NOT how `rejected` blocks submit
(rejected stays submit-only-to-resend).

Run: pytest tests/test_portal_si_responded_readonly.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.portal import PortalToken
from app.models.procurement import StockInquiry
from app.services.error_handler import AppException
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session

CONTACT_ID = "contact-abc"
SPACE_ID = "space-1"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _token() -> PortalToken:
    # _fetch_for_edit only reads contact_id / space_id off the token object.
    return PortalToken(
        token="t",
        contact_id=CONTACT_ID,
        space_id=SPACE_ID,
        expires_at=datetime(2099, 1, 1),
        verified_at=datetime(2026, 1, 1),
    )


def _si(db, status: str, **overrides) -> str:
    sid = str(uuid.uuid4())
    row = StockInquiry(
        id=sid,
        inquiry_number="SI26-9001",
        status=status,
        contact_id=CONTACT_ID,
        space_id=SPACE_ID,
        salesperson="Eric",
        product_code="SRTWT51030",
        item_description="Free Standing Bath Tub Mixer",
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return sid


def test_submit_draft_on_responded_raises(db):
    """The plain Submit path is closed for `responded` - Revise is the only door."""
    sid = _si(db, "responded")
    svc = PortalService(db)
    with pytest.raises(AppException) as ei:
        svc.submit_draft(_token(), "stock_inquiry", sid, payload=None)
    assert "responded" in str(ei.value).lower()
    row = db.get(StockInquiry, sid)
    assert row.status == "responded"


def test_create_or_update_draft_on_responded_raises_with_revise_copy(db):
    """Draft-save on a responded SI points the salesperson at Revise, not Submit."""
    sid = _si(db, "responded")
    svc = PortalService(db)
    with pytest.raises(AppException) as ei:
        svc.create_or_update_draft(
            _token(), "stock_inquiry", {"additional_remark": "park it"}, submission_id=sid
        )
    assert "can only be changed through revise" in str(ei.value).lower()


@pytest.mark.parametrize(
    "status,expected_editable",
    [
        ("responded", False),
        ("rejected", True),
        ("pending_purchasing", False),
    ],
)
def test_summary_is_editable_reflects_the_new_gate(db, status, expected_editable):
    sid = _si(db, status)
    svc = PortalService(db)
    summary = svc.get_submission(_token(), "stock_inquiry", sid)
    assert summary["is_editable"] is expected_editable


def test_summary_is_editable_true_for_portal_draft(db):
    """A row still parked in ``portal_draft_at`` stays editable regardless of status."""
    sid = _si(db, "pending_purchasing", portal_draft_at=datetime(2026, 1, 2))
    svc = PortalService(db)
    summary = svc.get_submission(_token(), "stock_inquiry", sid)
    assert summary["is_editable"] is True
