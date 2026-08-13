"""Maintaining the rates, and being told which ones are missing.

The plan cannot rank two prices in different money without a rate, and the buyer cannot
enter a rate they do not know they need. So this service does two jobs: it holds the rates,
and it reports which currencies the purchase-order book actually uses so the screen can say
"you have no rate for CNY" instead of leaving the buyer to work that out from a plan row
that quietly refuses to be funded.

Saving follows the same reconciliation rule as every other feed here: same then skip, diff
then update, new then create.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import currency_rate_service as svc
from app.services.scm.money import BASE_CURRENCY
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTFX"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with blank_session() as s:
        yield s


# --------------------------------------------------------------------------- #
# holding the rates
# --------------------------------------------------------------------------- #

def test_a_new_currency_is_created(db):
    svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1), note="bank")

    got = {r["currency"]: r for r in svc.list_rates(db)["rates"]}
    assert got["USD"]["rate_to_base"] == 4.4
    assert got["USD"]["as_of"] == "2026-08-01"
    assert got["USD"]["note"] == "bank"


def test_an_unchanged_rate_is_left_alone_rather_than_rewritten(db):
    """> "if same then skip, if diff then update, if new then create"

    Rewriting an identical row would move `updated_at`, and a buyer reading "updated
    today" would believe somebody had checked the rate today.
    """
    svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1))
    before = svc.list_rates(db)["rates"][0]["updated_at"]

    result = svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1))

    assert result["action"] == "unchanged"
    assert svc.list_rates(db)["rates"][0]["updated_at"] == before


def test_a_changed_rate_replaces_the_old_one_in_place(db):
    svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1))

    result = svc.upsert_rate(db, "USD", 4.7, as_of=date(2026, 8, 8))

    assert result["action"] == "updated"
    rates = svc.list_rates(db)["rates"]
    assert len(rates) == 1                       # in place, not a second row
    assert rates[0]["rate_to_base"] == 4.7


def test_case_and_padding_do_not_create_a_second_row_for_the_same_currency(db):
    svc.upsert_rate(db, "USD", 4.4)

    svc.upsert_rate(db, " usd ", 4.7)

    assert [r["currency"] for r in svc.list_rates(db)["rates"]] == ["USD"]


def test_the_base_currency_is_refused_rather_than_stored_as_one(db):
    """A stored 1 is a number somebody can edit to 0.9, and every ringgit figure in the
    system would silently move."""
    with pytest.raises(AppException) as e:
        svc.upsert_rate(db, BASE_CURRENCY, 1)

    assert BASE_CURRENCY in str(e.value.detail)


def test_a_non_positive_rate_is_refused(db):
    """Zero would zero out every price in that currency; negative would invert it."""
    for bad in (0, -4.4):
        with pytest.raises(AppException):
            svc.upsert_rate(db, "USD", bad)


def test_a_rate_can_be_removed(db):
    svc.upsert_rate(db, "USD", 4.4)

    svc.delete_rate(db, "usd")

    assert svc.list_rates(db)["rates"] == []


def test_removing_a_rate_nobody_entered_says_so(db):
    with pytest.raises(AppException) as e:
        svc.delete_rate(db, "USD")

    assert e.value.status_code == 404


# --------------------------------------------------------------------------- #
# telling the buyer which rates are missing
# --------------------------------------------------------------------------- #

def _priced_line(db, currency: str):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code(MARKER),
                      product_name=f"{MARKER} item", category_id=cat.id,
                      base_uom_id=uom.id, list_price=0, is_active=True,
                      is_discontinued=False)
    supplier = Supplier(id=_u(), supplier_code=unique_code("S"),
                        supplier_name=f"{MARKER} supplier")
    db.add_all([product, supplier])
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=unique_code(MARKER), supplier_id=supplier.id,
                       status="closed", issue_date=date(2026, 1, 1), currency=currency)
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(id=_u(), purchase_order_id=po.id, product_id=product.id,
                             qty_ordered=1, qty_received=1, unit_cost=10,
                             currency=currency, line_status="closed"))
    db.flush()


def test_a_currency_the_book_uses_with_no_rate_is_reported_as_missing(db):
    _priced_line(db, "CNY")

    assert svc.list_rates(db)["missing"] == ["CNY"]


def test_a_currency_that_has_a_rate_is_not_reported_as_missing(db):
    _priced_line(db, "CNY")
    svc.upsert_rate(db, "CNY", 0.62)

    assert svc.list_rates(db)["missing"] == []


def test_the_base_currency_is_never_reported_as_missing(db):
    """It needs no rate, so listing it would be a chore that cannot be completed."""
    _priced_line(db, BASE_CURRENCY)

    assert svc.list_rates(db)["missing"] == []


def test_the_base_currency_is_stated_so_the_screen_need_not_guess_it(db):
    assert svc.list_rates(db)["base_currency"] == BASE_CURRENCY
