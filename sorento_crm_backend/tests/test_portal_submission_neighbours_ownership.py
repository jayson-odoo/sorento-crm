"""HARD BLOCKER (UAC-response-attachments.md G2): portal record navigation.

``get_neighbours`` is token-scoped, never id-scoped: a token holder can never
page into another contact's submissions by guessing/adjusting the id in the
neighbours URL. Ownership is enforced by re-running ``get_submission`` (which
raises 403 OWNER_MISMATCH / 404) before any neighbour is computed.

Also covers G1 (position/total/prev/next, newest-first) and the "same kind
only" scoping (a PR neighbour set must not include the same contact's SF
rows, and a stock-inquiry set must not include another kind).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.portal import PortalToken
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.services.error_handler import AppException
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _token(contact_id: str, space_id: str) -> PortalToken:
    return PortalToken(
        token="t",
        contact_id=contact_id,
        space_id=space_id,
        expires_at=datetime(2099, 1, 1),
        verified_at=datetime(2026, 1, 1),
    )


def _si(db, *, contact_id, space_id, number, created_at) -> str:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=number,
        status="new",
        contact_id=contact_id,
        space_id=space_id,
    )
    db.add(row)
    db.commit()
    row.created_at = created_at
    db.commit()
    return str(row.id)


def _pr(db, *, contact_id, space_id, request_type, number, created_at) -> str:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number=number,
        contact_id=contact_id,
        space_id=space_id,
    )
    db.add(row)
    db.commit()
    row.created_at = created_at
    db.commit()
    return str(row.id)


# --------------------------------------------------------------------------
# G2 hard blocker: cannot page into another contact's submissions
# --------------------------------------------------------------------------


def test_neighbours_refuses_a_foreign_contacts_submission_id(db):
    a_id, b_id, space = "contact-a", "contact-b", "space-1"
    _si(db, contact_id=a_id, space_id=space, number="A-1", created_at=datetime(2026, 1, 1))
    b_inquiry = _si(db, contact_id=b_id, space_id=space, number="B-1", created_at=datetime(2026, 1, 2))

    svc = PortalService(db)
    with pytest.raises(AppException) as ei:
        svc.get_neighbours(_token(a_id, space), "stock_inquiry", b_inquiry)
    # get_submission's OWNER_MISMATCH path - row exists, but not for this token.
    assert ei.value.status_code in (403, 404)


def test_neighbours_refuses_a_completely_unknown_id(db):
    a_id, space = "contact-a", "space-1"
    _si(db, contact_id=a_id, space_id=space, number="A-1", created_at=datetime(2026, 1, 1))

    svc = PortalService(db)
    with pytest.raises(AppException) as ei:
        svc.get_neighbours(_token(a_id, space), "stock_inquiry", str(uuid.uuid4()))
    assert ei.value.status_code == 404


# --------------------------------------------------------------------------
# G1: position/total/prev/next, newest-first, scoped to the owner's own set
# --------------------------------------------------------------------------


def test_neighbours_position_total_prev_next_newest_first(db):
    a_id, b_id, space = "contact-a", "contact-b", "space-1"
    # Contact A: 3 inquiries, created in order oldest -> newest.
    oldest = _si(db, contact_id=a_id, space_id=space, number="A-OLD", created_at=datetime(2026, 1, 1))
    middle = _si(db, contact_id=a_id, space_id=space, number="A-MID", created_at=datetime(2026, 1, 2))
    newest = _si(db, contact_id=a_id, space_id=space, number="A-NEW", created_at=datetime(2026, 1, 3))
    # Contact B's own inquiry must never appear in A's neighbour set.
    _si(db, contact_id=b_id, space_id=space, number="B-1", created_at=datetime(2026, 1, 2, 12))

    svc = PortalService(db)
    token_a = _token(a_id, space)

    # Newest-first: position 1 = newest, position 3 = oldest.
    res_newest = svc.get_neighbours(token_a, "stock_inquiry", newest)
    assert res_newest == {"prev_id": None, "next_id": middle, "position": 1, "total": 3}

    res_middle = svc.get_neighbours(token_a, "stock_inquiry", middle)
    assert res_middle == {"prev_id": newest, "next_id": oldest, "position": 2, "total": 3}

    res_oldest = svc.get_neighbours(token_a, "stock_inquiry", oldest)
    assert res_oldest == {"prev_id": middle, "next_id": None, "position": 3, "total": 3}


def test_neighbours_same_kind_only_pr_and_sf_do_not_mix(db):
    a_id, space = "contact-a", "space-1"
    pr = _pr(
        db,
        contact_id=a_id,
        space_id=space,
        request_type="purchase_request",
        number="PR-1",
        created_at=datetime(2026, 1, 1),
    )
    # Same contact, same underlying table, different kind - must not be a neighbour.
    _pr(
        db,
        contact_id=a_id,
        space_id=space,
        request_type="sponsorship_form",
        number="SF-1",
        created_at=datetime(2026, 1, 2),
    )

    svc = PortalService(db)
    res = svc.get_neighbours(_token(a_id, space), "purchase_request", pr)
    assert res == {"prev_id": None, "next_id": None, "position": 1, "total": 1}


def test_neighbours_scoped_to_space_id_too(db):
    """A contact_id shared across two different space_id rows (unusual, but the
    ownership filter checks both columns) must not cross-contaminate."""
    a_id = "contact-a"
    own = _si(db, contact_id=a_id, space_id="space-1", number="S1-1", created_at=datetime(2026, 1, 1))
    _si(db, contact_id=a_id, space_id="space-2", number="S2-1", created_at=datetime(2026, 1, 2))

    svc = PortalService(db)
    res = svc.get_neighbours(_token(a_id, "space-1"), "stock_inquiry", own)
    assert res == {"prev_id": None, "next_id": None, "position": 1, "total": 1}
