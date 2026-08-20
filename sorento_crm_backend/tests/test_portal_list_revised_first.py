"""Portal list ordering: a revision reads as new work, so it sorts to the top.

``PortalService.list_submissions`` orders stock inquiries (and purchase
requests) by ``coalesce(last_revised_at, created_at) desc, id asc`` - a row
revised after two others were created jumps ahead of both, and every summary
carries ``revision_no`` / ``last_revised_at`` so the FE can badge it.

The CRM-side (non-portal) stock-inquiry list grows a matching ``last_activity_at``
sort key in ``StockInquiryService``'s sort map, for the office list to offer the
same "most recently active" ordering.

Run: pytest tests/test_portal_list_revised_first.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.portal import PortalToken
from app.models.procurement import StockInquiry
from app.services.portal_service import PortalService
from app.services.procurement_service import StockInquiryService
from tests._pg_fixture import blank_session

CONTACT_ID = "contact-revlist"
SPACE_ID = "space-revlist"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _token() -> PortalToken:
    return PortalToken(
        token="t",
        contact_id=CONTACT_ID,
        space_id=SPACE_ID,
        expires_at=datetime(2099, 1, 1),
        verified_at=datetime(2026, 1, 1),
    )


def _si(db, *, inquiry_number: str, created_at: datetime, **overrides) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=inquiry_number,
        status="pending_purchasing",
        contact_id=CONTACT_ID,
        space_id=SPACE_ID,
        salesperson="Eric",
        product_code="SRTWT51030",
        item_description="Free Standing Bath Tub Mixer",
        created_at=created_at,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return row


def test_a_revised_row_sorts_ahead_of_later_creates(db):
    now = datetime(2026, 6, 1, 12, 0, 0)
    row_a = _si(db, inquiry_number="SI26-A", created_at=now - timedelta(days=3))
    row_b = _si(db, inquiry_number="SI26-B", created_at=now - timedelta(days=2))
    row_c = _si(db, inquiry_number="SI26-C", created_at=now - timedelta(days=1))

    # A was created earliest but revised just now, so it reads as the freshest work.
    row_a.last_revised_at = now
    row_a.revision_no = 1
    db.add(row_a)
    db.commit()

    summaries = PortalService(db).list_submissions(_token(), "stock_inquiry")
    ids_in_order = [s["id"] for s in summaries]
    assert ids_in_order == [str(row_a.id), str(row_c.id), str(row_b.id)]

    for summary in summaries:
        assert "revision_no" in summary
        assert "last_revised_at" in summary

    revised = next(s for s in summaries if s["id"] == str(row_a.id))
    assert revised["revision_no"] == 1
    assert revised["last_revised_at"] is not None

    untouched = next(s for s in summaries if s["id"] == str(row_b.id))
    assert untouched["revision_no"] == 0
    assert untouched["last_revised_at"] is None


def test_crm_sort_map_accepts_last_activity_at(db):
    now = datetime(2026, 6, 1, 12, 0, 0)
    row_older_created_but_revised = _si(
        db,
        inquiry_number="SI26-CRM-A",
        created_at=now - timedelta(days=5),
        last_revised_at=now,
    )
    row_never_revised = _si(
        db,
        inquiry_number="SI26-CRM-B",
        created_at=now - timedelta(days=1),
    )

    result = StockInquiryService(db).list_inquiries(
        sort_field="last_activity_at",
        sort_dir="desc",
        contact_id=CONTACT_ID,
        space_id=SPACE_ID,
    )
    ids_in_order = [str(r.id) for r in result["data"]]
    assert ids_in_order == [str(row_older_created_but_revised.id), str(row_never_revised.id)]
