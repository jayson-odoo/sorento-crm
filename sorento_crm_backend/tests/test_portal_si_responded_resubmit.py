"""Portal: a `responded` stock inquiry is editable + resubmittable.

Purchasing sometimes hits respond (a clarifying question) when the intent is to
send the inquiry back for revision. The portal must let the salesperson edit and
resubmit a `responded` inquiry — mirroring the `rejected` path — landing it at
`pending_project_sales`. Draft-save stays disabled (submit-only), like `rejected`.

Run: pytest tests/test_portal_si_responded_resubmit.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

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


def _responded_si(db, **overrides) -> str:
    sid = str(uuid.uuid4())
    row = StockInquiry(
        id=sid,
        inquiry_number="SI26-9001",
        status="responded",
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


def test_fetch_for_edit_allows_responded_stock_inquiry(db):
    """The core gate: a responded SI is now editable (previously raised)."""
    sid = _responded_si(db)
    svc = PortalService(db)
    row = svc._fetch_for_edit("stock_inquiry", _token(), sid)
    assert row.id == sid
    assert row.status == "responded"


def test_submit_draft_from_responded_advances_to_pending_project_sales(db):
    sid = _responded_si(db)
    svc = PortalService(db)
    with patch.object(svc, "get_submission", return_value={}):
        svc.submit_draft(_token(), "stock_inquiry", sid, payload=None)
    row = db.get(StockInquiry, sid)
    assert row.status == "pending_project_sales"


def test_create_or_update_draft_blocks_responded(db):
    """Draft-save stays disabled on a responded SI — submit-only, like rejected."""
    sid = _responded_si(db)
    svc = PortalService(db)
    with pytest.raises(AppException) as ei:
        svc.create_or_update_draft(
            _token(), "stock_inquiry", {"additional_remark": "park it"}, submission_id=sid
        )
    assert "draft saves are disabled" in str(ei.value).lower()
