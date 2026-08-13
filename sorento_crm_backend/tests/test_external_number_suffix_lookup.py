"""A suffixed document number must still find its row (UAC section N6).

The highest-value test in the suffix slice, because the failure mode is silent.
The external API create endpoints use the document number as a resubmit key:

* ``POST /api/v1/external/stock-inquiries`` -> ``StockInquiryService.create_inquiry``
* ``POST /api/v1/external/purchase-requests`` -> ``PurchaseRequestService.upsert_external_request``

Both look the number up and, on a match with a rejected row, UPDATE it. Once an
outbound payload renders ``SI-26-0184-R2`` (N5), an external caller echoing that
number back would miss the row on an exact match and **insert a duplicate**
instead - data duplication on a live integration path, with a 201 and no error
anywhere. So the assertion is not "it resolves" but "there is still exactly ONE
row carrying that number".

Postgres only, on an empty scratch schema, seeding its own rows under a marker.

Run: venv/bin/pytest tests/test_external_number_suffix_lookup.py -q
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.schemas.external.procurement import PurchaseRequestExternalCreate
from app.schemas.procurement import StockInquiryCreate
from app.services.error_handler import AppException
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from tests._pg_fixture import blank_session

MARKER = "ZZT-NUMSUFFIX"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _number(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}"


# --------------------------------------------------------------- stock inquiry


def _rejected_inquiry(db, number: str, *, revision_no: int = 2) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=number,
        status="rejected",
        salesperson=f"{MARKER} salesperson",
        product_code=f"{MARKER}-P",
        item_description="Free standing bath tub mixer",
        project_customer=f"{MARKER} customer",
        project_name=f"{MARKER} project",
        quantity="4",
        delivery_date="2026-09-01",
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
        revision_no=revision_no,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _inquiry_payload(number: str) -> StockInquiryCreate:
    return StockInquiryCreate(
        inquiry_number=number,
        salesperson=f"{MARKER} salesperson",
        product_code=f"{MARKER}-P",
        item_description="Free standing bath tub mixer",
        project_customer=f"{MARKER} customer",
        project_name=f"{MARKER} project",
        quantity="9",
        delivery_date="2026-09-01",
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
        user_confirmed=True,
    )


def _inquiries_with(db, number: str) -> list[StockInquiry]:
    """Every row whose number starts with this one - so a duplicate stored under
    ANY suffix is counted, not just the one the test happened to send."""
    return (
        db.query(StockInquiry)
        .filter(StockInquiry.inquiry_number.like(f"{number}%"))
        .all()
    )


def test_suffixed_inquiry_number_resubmits_instead_of_duplicating(db):
    existing = _rejected_inquiry(db, _number("SI"))
    number = existing.inquiry_number

    row, outcome = StockInquiryService(db).create_inquiry(
        _inquiry_payload(f"{number}-R2"), require_user_confirmation=True
    )

    assert outcome == "resubmitted"
    assert str(row.id) == str(existing.id)
    # The one that actually matters: no second row was inserted, under either the
    # bare or the suffixed number.
    assert len(_inquiries_with(db, number)) == 1
    # The stored number stays bare (UAC N2) - the suffix is never persisted.
    assert row.inquiry_number == number
    assert row.quantity == "9"


def test_bare_inquiry_number_still_resubmits(db):
    """The unsuffixed path is unchanged - this is the regression guard on the change."""
    existing = _rejected_inquiry(db, _number("SI"), revision_no=0)

    row, outcome = StockInquiryService(db).create_inquiry(
        _inquiry_payload(existing.inquiry_number), require_user_confirmation=True
    )

    assert outcome == "resubmitted"
    assert str(row.id) == str(existing.id)
    assert len(_inquiries_with(db, existing.inquiry_number)) == 1


def test_a_suffixed_number_for_a_non_rejected_inquiry_is_refused_not_duplicated(db):
    """Stripping must not turn the "already exists" guard into a silent insert."""
    existing = _rejected_inquiry(db, _number("SI"))
    existing.status = "pending_purchasing"
    db.commit()

    with pytest.raises(AppException) as ei:
        StockInquiryService(db).create_inquiry(
            _inquiry_payload(f"{existing.inquiry_number}-R2"), require_user_confirmation=True
        )

    assert ei.value.status_code in (400, 422)
    db.rollback()
    assert len(_inquiries_with(db, existing.inquiry_number)) == 1


# ------------------------------------------------------------ purchase request


def _rejected_request(db, number: str, *, revision_no: int = 2) -> PurchaseRequestHeader:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_number=number,
        request_type="purchase_request",
        status="submitted",
        approval_status="rejected",
        source="external",
        customer_name=f"{MARKER} customer",
        project_title=f"{MARKER} project",
        purpose=f"{MARKER} purpose",
        requested_by=f"{MARKER} requester",
        # The completeness gate falls back to the existing row for a resubmit, and
        # the external create schema declares neither of these - see the note on
        # test_an_unknown_suffixed_number_creates_a_row_with_the_BARE_number.
        expected_delivery_date=date(2026, 9, 1),
        sales_type="project",
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
        revision_no=revision_no,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request_payload(number: str) -> PurchaseRequestExternalCreate:
    return PurchaseRequestExternalCreate(
        request_type="purchase_request",
        request_number=number,
        customer_name=f"{MARKER} customer",
        project_title=f"{MARKER} project",
        purpose=f"{MARKER} purpose",
        requested_by=f"{MARKER} requester",
        expected_po_date="2026-09-01",
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": "3"}],
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
        user_confirmed=True,
    )


def _sponsorship_payload(number: str) -> PurchaseRequestExternalCreate:
    return PurchaseRequestExternalCreate(
        request_type="sponsorship_form",
        request_number=number,
        sponsor_subject="Others",
        sponsor_subject_other=f"{MARKER} subject",
        customer_name=f"{MARKER} customer",
        date_of_delivery="2026-09-01",
        requested_by=f"{MARKER} requester",
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": "3"}],
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
        user_confirmed=True,
    )


def _requests_with(db, number: str) -> list[PurchaseRequestHeader]:
    """Every row whose number starts with this one - so a duplicate stored under
    ANY suffix is counted, not just the one the test happened to send."""
    return (
        db.query(PurchaseRequestHeader)
        .filter(PurchaseRequestHeader.request_number.like(f"{number}%"))
        .all()
    )


def test_suffixed_request_number_updates_instead_of_duplicating(db):
    existing = _rejected_request(db, _number("PR"))
    number = existing.request_number

    row, outcome = PurchaseRequestService(db).upsert_external_request(
        _request_payload(f"{number}-R2")
    )

    assert outcome == "updated"
    assert str(row.id) == str(existing.id)
    assert len(_requests_with(db, number)) == 1
    assert row.request_number == number


def test_bare_request_number_still_updates(db):
    existing = _rejected_request(db, _number("PR"), revision_no=0)

    row, outcome = PurchaseRequestService(db).upsert_external_request(
        _request_payload(existing.request_number)
    )

    assert outcome == "updated"
    assert str(row.id) == str(existing.id)
    assert len(_requests_with(db, existing.request_number)) == 1


def test_an_unknown_suffixed_number_creates_a_row_with_the_BARE_number(db):
    """No match is still a create - but the stored number must not carry "-R7".

    Persisting the suffix would bake a revision into the identity of a document
    that has never been revised, and every later lookup would then depend on the
    caller repeating the same suffix (UAC N2).

    Runs on a sponsorship form rather than a purchase request because
    ``PurchaseRequestExternalCreate`` declares no ``sales_type`` while
    ``_PR_REQUIRED_FIELDS_BY_TYPE`` requires one for ``purchase_request`` - so a
    brand-new external PR create cannot satisfy its own gate. Pre-existing, and
    unrelated to the number suffix.
    """
    number = _number("SF")

    row, outcome = PurchaseRequestService(db).upsert_external_request(
        _sponsorship_payload(f"{number}-R7")
    )

    assert outcome == "created"
    assert row.request_number == number
    assert len(_requests_with(db, number)) == 1
