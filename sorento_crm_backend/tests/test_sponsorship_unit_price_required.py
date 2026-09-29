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
from app.models.procurement import PurchaseRequestHeader, PurchaseRequestLine
from app.schemas.external.procurement import PurchaseRequestExternalCreate
from app.schemas.procurement import (
    PurchaseRequestHeaderCreate,
    PurchaseRequestHeaderUpdate,
    PurchaseRequestUpdateAndReply,
)
from app.services.error_handler import AppException
import app.services.form_sla_service as form_sla_service_mod
from app.services.portal_service import PortalService
from app.services.procurement_service import PurchaseRequestService
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


def test_internal_create_accepts_sponsorship_line_with_zero_unit_price():
    """AC-P8/Should fix 2: mandatory means present, not positive - a sponsored
    item can legitimately be free. 0 must not be refused."""
    data = PurchaseRequestHeaderCreate(
        request_type="sponsorship_form", products=[_internal_line(unit_price="0")]
    )
    assert data.products[0].unit_price == 0


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


def test_portal_first_save_draft_with_priceless_sponsorship_line_is_not_blocked(db):
    """Should fix 1 (review round 1, PR #1232): the CREATE branch of
    `create_or_update_draft` (`submission_id=None`, a dealer's very first Save
    Draft) must never be gated - that rule lives only in `submit_draft`. Prior
    coverage of AC-P4 only exercised the UPDATE branch, and only as a
    precondition step inside the submit-refusal test, never standalone."""
    contact_id = str(uuid.uuid4())
    contact = RespondContact(
        id=contact_id,
        phone_number="+6019" + uuid.uuid4().hex[:7],
        name=f"{MARKER} first-save dealer",
    )
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id=contact_id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add_all([contact, token])
    db.commit()

    result = PortalService(db).create_or_update_draft(
        token,
        "sponsorship_form",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2"}]},
        submission_id=None,
    )

    header = (
        db.query(PurchaseRequestHeader)
        .filter(PurchaseRequestHeader.id == result["id"])
        .one()
    )
    assert header.status == "draft"
    assert header.lines[0].unit_price is None


def test_portal_update_draft_with_priceless_sponsorship_line_is_not_blocked(db):
    """Should fix 1: the UPDATE branch, standalone rather than nested as a
    precondition inside `test_portal_submit_refuses_sponsorship_line_without_unit_price`."""
    token, header = _seed_portal_draft(db, kind="sponsorship_form")

    PortalService(db).create_or_update_draft(
        token,
        "sponsorship_form",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2", "unit_price": None}]},
        submission_id=str(header.id),
    )

    db.refresh(header)
    assert header.status == "draft"
    assert header.lines[0].unit_price is None


def test_portal_submit_accepts_sponsorship_line_with_zero_unit_price(db):
    """AC-P8/Should fix 2: 0 is a plausible real price for a sponsored item and
    must not be refused - "mandatory" means present, not positive."""
    token, header = _seed_portal_draft(db, kind="sponsorship_form")
    svc = PortalService(db)
    svc.create_or_update_draft(
        token,
        "sponsorship_form",
        {"products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2", "unit_price": "0"}]},
        submission_id=str(header.id),
    )

    svc.submit_draft(token, "sponsorship_form", str(header.id))

    db.refresh(header)
    assert header.status == "submitted"
    assert header.lines[0].unit_price == 0


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


# --------------------------------------------------------------------------- #
# 4. ProcurementService.update_request / update_request_and_reply - effective
#    type check (#1232 blocking 2). `request_type` is optional on
#    `PurchaseRequestHeaderUpdate` and usually absent on a plain header edit -
#    the rule must still hold against the STORED header's type when the
#    payload itself omits it, or a direct API caller bypasses the rule on a
#    stored sponsorship form simply by not sending request_type.
# --------------------------------------------------------------------------- #


def _seed_stored_sponsorship_request(db) -> PurchaseRequestHeader:
    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type="sponsorship_form",
        status="draft",
        source="system",
    )
    db.add(header)
    db.flush()
    db.add(
        PurchaseRequestLine(
            id=str(uuid.uuid4()),
            purchase_request_id=header.id,
            item_code=f"{MARKER}-ITEM",
            quantity=2,
            unit_price=10,
            total=20,
            sort_order=0,
        )
    )
    db.commit()
    db.refresh(header)
    return header


def test_update_request_refuses_priceless_line_when_request_type_omitted(db):
    header = _seed_stored_sponsorship_request(db)
    svc = PurchaseRequestService(db)
    data = PurchaseRequestHeaderUpdate(
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": 2}]
    )
    assert data.request_type is None

    with pytest.raises(AppException) as ei:
        svc.update_request(str(header.id), data)

    _assert_line_refusal(ei.value)
    db.rollback()


def test_update_request_accepts_priceless_line_when_explicitly_purchase_request(db):
    """The effective-type check must still respect an explicit override: a
    stored sponsorship form's type is only inferred as a fallback, never
    forced, so a payload that (validly) changes the type away from
    sponsorship_form is unaffected."""
    header = _seed_stored_sponsorship_request(db)
    svc = PurchaseRequestService(db)
    data = PurchaseRequestHeaderUpdate(
        request_type="purchase_request",
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": 2}],
    )

    updated = svc.update_request(str(header.id), data)

    assert updated.request_type == "purchase_request"
    assert updated.lines[0].unit_price is None


def test_update_request_and_reply_refuses_priceless_line_when_request_type_omitted(db):
    header = _seed_stored_sponsorship_request(db)
    svc = PurchaseRequestService(db)
    data = PurchaseRequestUpdateAndReply(
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": 2}],
        reply_message="hi",
    )
    assert data.request_type is None

    with pytest.raises(AppException) as ei:
        svc.update_request_and_reply(str(header.id), data, respond_user_id=f"{MARKER}-user")

    _assert_line_refusal(ei.value)
    db.rollback()


def _seed_revisable_sponsorship_form(db):
    """Uses `tests/_revision_harness.py`'s own seeding (not a test module itself -
    see its docstring - so importable here) for the config/contact/token/entity a
    revise needs, rather than reinventing it."""
    from tests._revision_harness import seed_config, seed_contact, seed_entity, seed_system_settings, seed_token

    seed_system_settings(db, cap=3)
    seed_config(db, "sponsorship_form")
    contact = seed_contact(db)
    row = seed_entity(db, "sponsorship_form", contact)
    token = seed_token(contact)
    return token, row


def _revise_sponsorship_form(db, *, products):
    from app.services.portal_revision_service import PortalRevisionService

    token, row = _seed_revisable_sponsorship_form(db)
    return PortalRevisionService(db).revise(
        token,
        "sponsorship_form",
        str(row.id),
        {"project_title": "Revised project", "products": products},
        "Corrected the price",
        row.revision_no,
    ), row


def _revise_purchase_request(db, *, products):
    from app.services.portal_revision_service import PortalRevisionService
    from tests._revision_harness import seed_config, seed_contact, seed_entity, seed_system_settings, seed_token

    seed_system_settings(db, cap=3)
    seed_config(db, "purchase_request")
    contact = seed_contact(db)
    row = seed_entity(db, "purchase_request", contact)
    token = seed_token(contact)
    return PortalRevisionService(db).revise(
        token,
        "purchase_request",
        str(row.id),
        {"project_title": "Revised project", "products": products},
        "Corrected the quantity",
        row.revision_no,
    ), row


def test_portal_revise_refuses_sponsorship_line_without_unit_price(db):
    from app.services.portal_revision_service import PortalRevisionService

    token, row = _seed_revisable_sponsorship_form(db)
    original_lines = [
        (line.item_code, str(line.quantity), str(line.unit_price)) for line in row.lines
    ]
    original_revision_no = row.revision_no

    with pytest.raises(AppException) as ei:
        PortalRevisionService(db).revise(
            token,
            "sponsorship_form",
            str(row.id),
            {
                "project_title": "Revised project",
                "products": [{"item_code": f"{MARKER}-ITEM", "quantity": "2"}],
            },
            "Corrected the price",
            row.revision_no,
        )

    _assert_line_refusal(ei.value)

    # #1232 round 2, nit 3: the gate sits after `apply_lines` + flush but before
    # the only commit (portal_revision_service.py:1646), so a rollback here
    # proves what a real request boundary would - the stored lines and
    # revision_no are untouched, not merely that the exception was raised.
    db.rollback()
    stored_lines = [
        (line.item_code, str(line.quantity), str(line.unit_price)) for line in row.lines
    ]
    assert stored_lines == original_lines
    assert row.revision_no == original_revision_no


def test_portal_revise_accepts_sponsorship_line_with_unit_price(db):
    _, row = _revise_sponsorship_form(
        db,
        products=[{"item_code": f"{MARKER}-ITEM", "quantity": "2", "unit_price": "15"}],
    )

    db.refresh(row)
    assert row.revision_no == 1


def test_portal_revise_purchase_request_line_without_unit_price_is_unchanged(db):
    """The gate only ever fires for sponsorship_form - a purchase request revise
    with the same price-less products payload must go through unaffected."""
    _, row = _revise_purchase_request(
        db, products=[{"item_code": f"{MARKER}-ITEM", "quantity": "2"}]
    )

    db.refresh(row)
    assert row.revision_no == 1


def test_update_request_with_no_products_key_is_unaffected_by_effective_type(db):
    """An edit that never touches lines (`products` omitted) is a no-op for this
    rule regardless of whether request_type is sent - matches
    `test_internal_update_with_no_products_key_is_a_no_op` for the schema layer."""
    header = _seed_stored_sponsorship_request(db)
    svc = PurchaseRequestService(db)
    data = PurchaseRequestHeaderUpdate(customer_name=f"{MARKER} updated")

    updated = svc.update_request(str(header.id), data)

    assert updated.customer_name == f"{MARKER} updated"
