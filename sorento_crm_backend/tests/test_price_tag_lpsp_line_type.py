"""PRICETAG-LPSP S2: LP or SP is a fact of the LINE, not only of the request.

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md, AC-1 to AC-5, AC-7.

Written test-FIRST (PRINCIPLES.md Phase 2). `price_tag_request_lines.price_type` does not exist
yet: each case is red as an unknown column / ignored key, never as a harness error.

Effective type of a line = `line.price_type or request.price_mode`; a line saved without a
type is stored with the request's mode (AC-2). The manual-price rules of
`_validate_line_price_basis` are judged against that effective type.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestLine
from app.services.error_handler import AppException
from app.services.price_tag_request_service import PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
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


def _line_of(db, request, product) -> PriceTagRequestLine:
    db.expire_all()
    return (
        db.query(PriceTagRequestLine)
        .filter_by(request_id=request.id, product_id=product.id)
        .one()
    )


def _row_of(db, request, product) -> dict:
    line = _line_of(db, request, product)
    return next(r for r in seed.rows(db, request) if r["line_id"] == line.id)


def _refusal(db, lines, *, price_mode) -> dict:
    """The wire dict of the AppException a save raises, nothing left behind."""
    savepoint = db.begin_nested()
    try:
        with pytest.raises(AppException) as exc:
            seed.submit(db, lines, price_mode=price_mode)
    finally:
        savepoint.rollback()
    assert exc.value.status_code == 422
    return exc.value.detail


# --------------------------------------------------------------------------- AC-1
def test_a_list_request_can_carry_an_sp_line(db):
    a = seed.product(db, "ZZLA", list_price="1000.00")
    b = seed.product(db, "ZZLB", list_price="800.00")
    request = seed.submit(
        db,
        [
            seed.line_dict(a, price_type="list"),
            seed.line_dict(b, price_type="selling", manual_sell_price=D("599")),
        ],
        price_mode="list",
    )
    line_a, line_b = _line_of(db, request, a), _line_of(db, request, b)
    assert line_a.price_type == "list"
    assert line_b.price_type == "selling"
    assert line_a.show_promo_price is False
    assert line_b.show_promo_price is True
    assert line_b.manual_sell_price == D("599")


def test_a_selling_request_can_carry_an_lp_line(db):
    a = seed.product(db, "ZZLC", list_price="1000.00")
    b = seed.product(db, "ZZLD", list_price="800.00")
    request = seed.submit(
        db,
        [
            seed.line_dict(a, price_type="list"),
            seed.line_dict(b, price_type="selling", manual_sell_price=D("599")),
        ],
        price_mode="selling",
    )
    assert _line_of(db, request, a).show_promo_price is False
    assert _line_of(db, request, b).show_promo_price is True


def test_replace_lines_stores_each_lines_type(db):
    a = seed.product(db, "ZZLE", list_price="1000.00")
    b = seed.product(db, "ZZLF", list_price="800.00")
    request = seed.submit(db, [seed.line_dict(a)], price_mode="list")
    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            seed.line_dict(a, price_type="selling", manual_sell_price=D("700")),
            seed.line_dict(b, price_type="list"),
        ],
    )
    db.flush()
    assert _line_of(db, request, a).price_type == "selling"
    assert _line_of(db, request, a).show_promo_price is True
    assert _line_of(db, request, b).price_type == "list"


def test_an_unknown_price_type_is_refused_by_the_schema():
    from pydantic import ValidationError

    from app.schemas.price_tag import PriceTagRequestLineCreate

    ok = PriceTagRequestLineCreate(line_type="product", price_type="selling")
    assert ok.price_type == "selling"
    assert PriceTagRequestLineCreate(line_type="product").price_type is None
    with pytest.raises(ValidationError):
        PriceTagRequestLineCreate(line_type="product", price_type="bogus")


def test_the_line_response_declares_price_type():
    from app.schemas.price_tag import PriceTagRequestLineResponse

    assert "price_type" in PriceTagRequestLineResponse.model_fields


# --------------------------------------------------------------------------- AC-2
@pytest.mark.parametrize("mode", ["list", "selling"])
def test_a_line_without_a_type_takes_the_requests_mode_and_stores_it(db, mode):
    a = seed.product(db, "ZZLG", list_price="1000.00")
    request = seed.submit(db, [seed.line_dict(a)], price_mode=mode)
    assert _line_of(db, request, a).price_type == mode


# --------------------------------------------------------------------------- AC-3
def test_manual_sp_on_an_lp_line_is_refused_even_in_a_selling_request(db):
    a = seed.product(db, "ZZLH", list_price="1000.00")
    detail = _refusal(
        db,
        [seed.line_dict(a, price_type="list", manual_sell_price=D("599"))],
        price_mode="selling",
    )
    assert detail["code"] == "INVALID_LINE_PRICE"
    assert detail["detail"] == "line:0"


def test_manual_sp_on_an_sp_line_of_a_list_request_is_accepted(db):
    a = seed.product(db, "ZZLI", list_price="1000.00")
    request = seed.submit(
        db,
        [seed.line_dict(a, price_type="selling", manual_sell_price=D("599"))],
        price_mode="list",
    )
    assert _line_of(db, request, a).manual_sell_price == D("599")


def test_manual_sp_with_no_line_type_follows_the_request_mode(db):
    a = seed.product(db, "ZZLJ", list_price="1000.00")
    detail = _refusal(
        db, [seed.line_dict(a, manual_sell_price=D("599"))], price_mode="list"
    )
    assert detail["code"] == "INVALID_LINE_PRICE"
    request = seed.submit(
        db, [seed.line_dict(a, manual_sell_price=D("599"))], price_mode="selling"
    )
    assert _line_of(db, request, a).manual_sell_price == D("599")


def test_the_second_line_is_the_one_named_when_only_it_is_wrong(db):
    a = seed.product(db, "ZZLK", list_price="1000.00")
    b = seed.product(db, "ZZLL", list_price="800.00")
    detail = _refusal(
        db,
        [
            seed.line_dict(a, price_type="selling", manual_sell_price=D("599")),
            seed.line_dict(b, price_type="list", manual_sell_price=D("500")),
        ],
        price_mode="selling",
    )
    assert detail["detail"] == "line:1"


def test_the_crm_price_patch_judges_the_lines_own_type(db):
    a = seed.product(db, "ZZLM", list_price="1000.00")
    b = seed.product(db, "ZZLN", list_price="800.00")
    request = seed.submit(
        db,
        [seed.line_dict(a, price_type="list"), seed.line_dict(b, price_type="selling")],
        price_mode="selling",
    )
    line_a, line_b = _line_of(db, request, a), _line_of(db, request, b)

    savepoint = db.begin_nested()
    with pytest.raises(AppException) as exc:
        PriceTagRequestService.set_line_price(
            db, request, line_a, {"manual_sell_price": D("599")}
        )
    savepoint.rollback()
    assert exc.value.detail["code"] == "INVALID_LINE_PRICE"

    PriceTagRequestService.set_line_price(db, request, line_b, {"manual_sell_price": D("599")})
    assert line_b.manual_sell_price == D("599")
    assert line_b.show_promo_price is True


def test_the_crm_price_patch_accepts_manual_sp_on_an_sp_line_of_a_list_request(db):
    a = seed.product(db, "ZZLO", list_price="1000.00")
    request = seed.submit(db, [seed.line_dict(a, price_type="selling")], price_mode="list")
    line = _line_of(db, request, a)
    PriceTagRequestService.set_line_price(db, request, line, {"manual_sell_price": D("640")})
    assert line.manual_sell_price == D("640")
    assert line.show_promo_price is True


# --------------------------------------------------------------------------- AC-4
@pytest.mark.parametrize("mode", ["list", "selling"])
def test_manual_sp_together_with_a_promotion_is_still_refused(db, mode):
    a = seed.product(db, "ZZLP", list_price="1000.00")
    promo = seed.promotion(db, [(a, "800.00")])
    detail = _refusal(
        db,
        [
            seed.line_dict(
                a, price_type="selling", promotion_id=promo.id, manual_sell_price=D("599")
            )
        ],
        price_mode=mode,
    )
    assert detail["code"] == "INVALID_LINE_PRICE"


# --------------------------------------------------------------------------- AC-5
def test_resolved_tag_data_follows_each_lines_type(db):
    a = seed.product(db, "ZZLQ", list_price="1000.00")
    b = seed.product(db, "ZZLR", list_price="800.00")
    c = seed.product(db, "ZZLS", list_price="500.00")
    promo = seed.promotion(db, [(c, "450.00")])
    request = seed.submit(
        db,
        [
            seed.line_dict(a, price_type="list"),
            seed.line_dict(b, price_type="selling", manual_sell_price=D("599")),
            seed.line_dict(c, price_type="selling", promotion_id=promo.id),
        ],
        price_mode="list",
    )
    lp, typed_sp, promo_sp = (_row_of(db, request, p) for p in (a, b, c))
    assert lp["show_promo_price"] is False
    assert lp["list_price"] == D("1000.00")
    assert typed_sp["show_promo_price"] is True
    assert typed_sp["sell_price"] == D("599")
    assert promo_sp["show_promo_price"] is True
    assert promo_sp["sell_price"] == D("450.00")


def test_an_lp_line_of_a_selling_request_resolves_as_lp(db):
    a = seed.product(db, "ZZLT", list_price="1000.00")
    c = seed.product(db, "ZZLU", list_price="500.00")
    promo = seed.promotion(db, [(a, "800.00"), (c, "450.00")])
    request = seed.submit(
        db,
        [
            seed.line_dict(a, price_type="list", promotion_id=promo.id),
            seed.line_dict(c, price_type="selling", promotion_id=promo.id),
        ],
        price_mode="selling",
    )
    assert _row_of(db, request, a)["show_promo_price"] is False
    assert _row_of(db, request, c)["show_promo_price"] is True


def test_old_lines_without_a_stored_type_follow_the_header(db):
    a = seed.product(db, "ZZLV", list_price="1000.00")
    request = seed.submit(
        db, [seed.line_dict(a, manual_sell_price=D("700"))], price_mode="selling"
    )
    line = _line_of(db, request, a)
    line.price_type = None  # a row as it was before the backfill
    db.flush()
    assert _row_of(db, request, a)["show_promo_price"] is True


def test_preview_of_unsaved_lines_honours_each_lines_type(db):
    from app.models.base import company_scope
    from app.services.dealer_kit import product_tag_template_service
    from app.services.dealer_kit.viewer import ViewerContext

    a = seed.product(db, "ZZLW", list_price="1000.00")
    b = seed.product(db, "ZZLX", list_price="800.00")
    with company_scope(db, frozenset({seed.SORENTO})):
        out = product_tag_template_service.preview(
            db,
            price_mode="list",
            lines=[
                {"key": "k1", "line_type": "product", "product_id": a.id,
                 "price_type": "list"},
                {"key": "k2", "line_type": "product", "product_id": b.id,
                 "price_type": "selling", "manual_sell_price": D("599")},
            ],
            viewer=ViewerContext(is_staff=True, is_internal_copy=True),
        )
    by_code = {row["code"]: row for row in out["lines"]}
    assert by_code[a.product_code]["show_promo_price"] is False
    assert by_code[b.product_code]["show_promo_price"] is True
    assert by_code[b.product_code]["sell_price"] == D("599")


def test_the_preview_line_schema_accepts_price_type():
    from app.schemas.price_tag import TagPreviewLineIn

    line = TagPreviewLineIn(key="k", line_type="product", price_type="selling")
    assert line.price_type == "selling"
    assert TagPreviewLineIn(key="k", line_type="product").price_type is None


# --------------------------------------------------------------------------- AC-7
def test_a_no_selling_price_brand_prints_the_typed_sp_on_an_sp_line(db):
    from app.models.product import Brand

    cabana = seed.product(db, "ZZLCAB", list_price="450.00")
    db.get(Brand, cabana.brand_id).no_promo_selling_price = True
    db.flush()

    request = seed.submit(
        db,
        [seed.line_dict(cabana, price_type="selling", manual_sell_price=D("399"))],
        price_mode="list",
    )
    line = _line_of(db, request, cabana)
    assert line.price_type == "selling"
    assert line.show_promo_price is True
    row = _row_of(db, request, cabana)
    assert row["show_promo_price"] is True
    assert row["sell_price"] == D("399")
    assert row["list_price"] == D("450.00")
