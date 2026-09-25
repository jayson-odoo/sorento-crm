"""#1227: unit price is mandatory on every sponsorship form line, on portal
submission and on system create/edit - purchase requests are unchanged.

Three surfaces, all refusing with the same detail shape
`price_tag_request_service` uses for a line refusal (`detail=f"line:<index>"`,
`code="SPONSORSHIP_UNIT_PRICE_REQUIRED"`), so a caller can name the offending
line the same way it already does for a price tag request line:

1. The external API (`PurchaseRequestExternalCreate`, `app/api/v1/external/purchase_requests.py`) -
   the WhatsApp/n8n ingest path.
2. The internal create/update schemas (`PurchaseRequestHeaderCreate` /
   `PurchaseRequestHeaderUpdate`, `app/schemas/procurement.py`) - the system
   procurement-management form.
3. `PortalService.submit_draft` (`app/services/portal_service.py`) - the dealer
   web portal's own submission flow, which builds `PurchaseRequestLine` rows
   directly from the raw payload rather than through either schema above, so it
   needs its own gate (mirroring the existing sponsorship project-requirement
   gate already in that method).

Draft save is deliberately unaffected everywhere: a draft may legitimately be
incomplete (see the existing project-requirement gate's own comment in
`submit_draft`). Only a submit - or a create/edit, which system staff use
in place of a draft - is refused.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.procurement import PurchaseRequestHeader
from app.schemas.external.procurement import PurchaseRequestExternalCreate
from app.schemas.procurement import PurchaseRequestHeaderCreate, PurchaseRequestHeaderUpdate
from app.services.error_handler import AppException
import app.services.form_sla_service as form_sla_service_mod
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session

MARKER = "ZZT-SPUP"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _neutralize_submit_side_effects(monkeypatch):
    """A successful submit also generates a document number, fires
    notifications + SLA events, and re-serializes via get_submission - none of
    which this suite is about."""
    monkeypatch.setattr(
        PortalService, "_assign_document_number_if_missing", lambda self, kind, row: None
    )
    monkeypatch.setattr(PortalService, "_post_submit_notify", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        PortalService, "get_submission", lambda self, token, kind, sid: {"id": sid}
    )
    monkeypatch.setattr(
        form_sla_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


def _assert_line_refusal(exc: AppException, *, index: int = 0) -> None:
    assert exc.status_code == 422
    assert exc.detail["detail"] == f"line:{index}"
    assert exc.detail["code"] == "SPONSORSHIP_UNIT_PRICE_REQUIRED"
    assert "unit price" in exc.detail["message"].lower()


# --------------------------------------------------------------------------- #
# 1. External API schema (WhatsApp/n8n ingest)
# --------------------------------------------------------------------------- #


def _external_line(**overrides) -> dict:
    line = {"item_code": f"{MARKER}-ITEM", "quantity": "3", "unit_price": "10.00"}
    line.update(overrides)
    return line


def _external_payload(request_type: str, line: dict) -> dict:
    return dict(
        request_type=request_type,
        customer_name=f"{MARKER} customer",
        sponsor_subject="showroom",
        date_of_delivery="2026-09-01",
        requested_by=f"{MARKER} requester",
        products=[line],
        contact_id=f"{MARKER}-contact",
        space_id=f"{MARKER}-space",
    )


@pytest.mark.parametrize(
    "bad_line",
    [
        _external_line(unit_price=None),
        _external_line(unit_price=""),
        _external_line(unit_price="-1"),
    ],
    ids=["missing", "blank", "negative"],
)
def test_external_create_refuses_sponsorship_line_without_unit_price(bad_line):
    with pytest.raises(AppException) as ei:
        PurchaseRequestExternalCreate(**_external_payload("sponsorship_form", bad_line))
    _assert_line_refusal(ei.value)


def test_external_create_accepts_sponsorship_line_with_unit_price():
    payload = PurchaseRequestExternalCreate(
        **_external_payload("sponsorship_form", _external_line())
    )
    assert payload.products[0].unit_price is not None


def test_external_create_purchase_request_line_without_unit_price_is_unchanged():
    payload = PurchaseRequestExternalCreate(
        **_external_payload("purchase_request", _external_line(unit_price=None))
    )
    assert payload.products[0].unit_price is None


# --------------------------------------------------------------------------- #
# 2. Internal create/update schemas (system procurement-management form)
# --------------------------------------------------------------------------- #


def _internal_line(**overrides) -> dict:
    line = {"item_code": f"{MARKER}-ITEM", "quantity": 3, "unit_price": "10.00"}
    line.update(overrides)
    return line


@pytest.mark.parametrize(
    "bad_line",
    [
        _internal_line(unit_price=None),
        _internal_line(unit_price=""),
        _internal_line(unit_price="-1"),
    ],
    ids=["missing", "blank", "negative"],
)
def test_internal_create_refuses_sponsorship_line_without_unit_price(bad_line):
    with pytest.raises(AppException) as ei:
        PurchaseRequestHeaderCreate(request_type="sponsorship_form", products=[bad_line])
    _assert_line_refusal(ei.value)


def test_internal_create_accepts_sponsorship_line_with_unit_price():
    data = PurchaseRequestHeaderCreate(
        request_type="sponsorship_form", products=[_internal_line()]
    )
    assert data.products[0].unit_price is not None


def test_internal_create_purchase_request_line_without_unit_price_is_unchanged():
    data = PurchaseRequestHeaderCreate(
        request_type="purchase_request", products=[_internal_line(unit_price=None)]
    )
    assert data.products[0].unit_price is None


@pytest.mark.parametrize(
    "bad_line",
    [
        _internal_line(unit_price=None),
        _internal_line(unit_price=""),
        _internal_line(unit_price="-1"),
    ],
    ids=["missing", "blank", "negative"],
)
def test_internal_update_refuses_sponsorship_line_without_unit_price(bad_line):
    with pytest.raises(AppException) as ei:
        PurchaseRequestHeaderUpdate(request_type="sponsorship_form", products=[bad_line])
    _assert_line_refusal(ei.value)


def test_internal_update_accepts_sponsorship_line_with_unit_price():
    data = PurchaseRequestHeaderUpdate(
        request_type="sponsorship_form", products=[_internal_line()]
    )
    assert data.products[0].unit_price is not None


def test_internal_update_with_no_products_key_is_a_no_op():
    """An edit that does not touch lines at all (`products` omitted, not `[]`)
    must not be refused for lines it never sent."""
    data = PurchaseRequestHeaderUpdate(request_type="sponsorship_form")
    assert data.products is None


# --------------------------------------------------------------------------- #
# 3. PortalService.submit_draft (the dealer web portal)
# --------------------------------------------------------------------------- #


def _seed_portal_draft(db, *, kind: str) -> tuple[PortalToken, PurchaseRequestHeader]:
    contact_id = str(uuid.uuid4())
    contact = RespondContact(
        id=contact_id,
        phone_number="+6019" + uuid.uuid4().hex[:7],
        name=f"{MARKER} portal submitter",
    )
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id=contact_id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=kind,
        status="draft",
        source="portal",
        contact_id=contact_id,
        space_id="space-1",
        portal_draft_at=datetime.utcnow(),
    )
    db.add_all([contact, token, header])
    db.commit()
    return token, header


@pytest.mark.parametrize(
    "unit_price",
    [None, "", "-5"],
    ids=["missing", "blank", "negative"],
)
def test_portal_submit_refuses_sponsorship_line_without_unit_price(db, unit_price):
    token, header = _seed_portal_draft(db, kind="sponsorship_form")
    svc = PortalService(db)
    # A draft save with an incomplete line is allowed - the gate is on submit,
    # matching the existing project-requirement gate's own reasoning.
    svc.create_or_update_draft(
        token,
        "sponsorship_form",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2", "unit_price": unit_price}]},
        submission_id=str(header.id),
    )

    with pytest.raises(AppException) as ei:
        svc.submit_draft(token, "sponsorship_form", str(header.id))

    _assert_line_refusal(ei.value)
    db.rollback()
    db.refresh(header)
    assert header.status == "draft"


def test_portal_submit_accepts_sponsorship_line_with_unit_price(db):
    token, header = _seed_portal_draft(db, kind="sponsorship_form")
    svc = PortalService(db)
    svc.create_or_update_draft(
        token,
        "sponsorship_form",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2", "unit_price": "10.00"}]},
        submission_id=str(header.id),
    )

    svc.submit_draft(token, "sponsorship_form", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"


def test_portal_submit_purchase_request_line_without_unit_price_is_unchanged(db):
    token, header = _seed_portal_draft(db, kind="purchase_request")
    svc = PortalService(db)
    svc.create_or_update_draft(
        token,
        "purchase_request",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2"}]},
        submission_id=str(header.id),
    )

    svc.submit_draft(token, "purchase_request", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"


def test_portal_submit_with_no_lines_is_unaffected(db):
    """A header with zero lines has nothing to refuse - regression guard for the
    pre-existing `test_pr_submitted_at.py` coverage, which submits with no lines
    at all."""
    token, header = _seed_portal_draft(db, kind="sponsorship_form")
    PortalService(db).submit_draft(token, "sponsorship_form", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"
