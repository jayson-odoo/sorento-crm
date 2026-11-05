"""PRICETAG-COMBO-RENDER fix round 3 (FAIL 1): the server refuses to approve a combo line that would print no price.

A combo line prints the combo's stored price or nothing (K8). Approve (the salesperson's own
proof) is refused with COMBO_PRICE_MISSING, detail `line:<index>`, when an LP line has no combo
list price or an SP line has no selling price. The check reads the tag's own resolver. Escalate
(hand it to marketing, who can fill the price) stays open.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.error_handler import AppException
from app.services.price_tag_request_service import STATUS_PROOF_READY, PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

D = Decimal


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )


def _own_proof(db, s, *, price_mode, **line_extra):
    request = seed.submit_one(
        db, s["host"], s["combo"], shapes.pick_parts(s["group"], s["options"][0]),
        price_mode=price_mode, **line_extra,
    )
    request.status = STATUS_PROOF_READY
    request.assigned_to_id = None
    db.flush()
    return request


def _refusal(db, request):
    with pytest.raises(AppException) as raised:
        PriceTagRequestService.require_combo_prices(db, request)
    return raised.value


def test_an_lp_combo_line_with_no_combo_list_price_is_refused(db):
    request = _own_proof(db, shapes.s3(db), price_mode="list")
    error = _refusal(db, request)
    assert error.status_code == 422
    assert error.detail["code"] == "COMBO_PRICE_MISSING"
    assert error.detail["detail"] == "line:0"


def test_an_sp_combo_line_with_no_selling_price_is_refused(db):
    error = _refusal(db, _own_proof(db, shapes.s3(db), price_mode="selling"))
    assert (error.detail["code"], error.detail["detail"]) == ("COMBO_PRICE_MISSING", "line:0")


def test_a_typed_selling_price_is_a_price(db):
    request = _own_proof(db, shapes.s3(db), price_mode="selling", manual_sell_price="1234.00")
    PriceTagRequestService.require_combo_prices(db, request)


def test_a_stored_combo_price_is_a_price(db):
    s = shapes.s3(db, list_price=D("900.00"), sell_price=D("800.00"))
    for mode in ("list", "selling"):
        PriceTagRequestService.require_combo_prices(db, _own_proof(db, s, price_mode=mode))


def test_the_second_line_is_named_by_its_position(db):
    s = shapes.s3(db, list_price=D("900.00"))
    t = shapes.s4(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(s["host"], s["combo"], shapes.pick_parts(s["group"], s["options"][0])),
            seed.line_dict(t["host"], t["combo"], shapes.fixed_parts(*t["fixed"])),
        ],
        price_mode="list",
    )
    assert _refusal(db, request).detail["detail"] == "line:1"


def test_a_line_without_a_combo_is_never_refused(db):
    s = shapes.s3(db)
    request = seed.submit_one(db, s["host"], None, shapes.pick_parts("Finish", *s["options"]), price_mode="list")
    PriceTagRequestService.require_combo_prices(db, request)


def test_self_approve_refuses_before_anything_is_written(db):
    request = _own_proof(db, shapes.s3(db), price_mode="list")
    with pytest.raises(AppException) as raised:
        PriceTagRequestService.self_approve(db, request, {"kind": "tag_sheet"}, "Sales")
    assert raised.value.detail["code"] == "COMBO_PRICE_MISSING"
    assert request.status == STATUS_PROOF_READY


def test_escalate_still_works_for_such_a_line(db):
    request = _own_proof(db, shapes.s3(db), price_mode="list")
    result = PriceTagRequestService.escalate(db, request, "No combo list price yet", request.contact_id)
    assert result.status != STATUS_PROOF_READY
