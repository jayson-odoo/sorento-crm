"""Fix lane round 2, F7: a unit price and an amount on every opportunity line.

Owner ruling (PR #1296, 27 Sep 11:48 MYT): "I create slaes opportuniesi, and i add product, but
my product no price one wor, hmm cause the product selling price i think by default we can put
the product price in the dealer flyer".

- A line carries `unit_price`; left out (or null) it takes the product's list price, the price
  the dealer flyer prints (`dealer_kit.pricing`), and a list price of zero means no price
  (`_a_real_price`), so the line stays unpriced rather than quoting RM 0.00.
- A typed `unit_price` is kept as typed.
- The response carries `line_amount` = qty x unit_price, null when unpriced.
- `expected_amount` left out on create defaults to the sum of the line amounts (0 with none).
- The portal product lookup carries the same `list_price`, so the form can prefill it.
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

from app.main import app  # noqa: F401  (first app import, see the S2 portal tests)

from tests._pg_fixture import blank_session
from tests.test_portal_sales_opportunities_s2 import (
    _agent as _portal_agent,
    _contact,
    _grant_kind,
    _portal_client,
    _seed,
)
from tests.test_sales_opportunities_s2 import BASE, _customer, _product, api, world  # noqa: F401

PORTAL = "/api/v1/public/portal/sales-opportunities"


def _post(client, url, customer_id=None, **payload):
    body = {"title": "ZZT priced", "expected_close_date": "2026-11-01", **payload}
    if customer_id:
        body["customer_id"] = customer_id
    return client.post(url, json=body)


def _unpriced_product(db):
    product = _product(db, name="ZZT No Price")
    product.list_price = Decimal("0.00")
    db.flush()
    return product


def test_f7_line_without_a_price_takes_the_products_list_price(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)  # list price 100.00
    res = _post(
        client, BASE, customer.id, expected_amount="1", lines=[{"product_id": product.id, "qty": "3"}]
    )
    assert res.status_code == 201, res.text
    line = res.json()["lines"][0]
    assert Decimal(line["unit_price"]) == Decimal("100.00")
    assert Decimal(line["line_amount"]) == Decimal("300.00")


def test_f7_a_typed_unit_price_is_kept(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = _post(
        client,
        BASE,
        customer.id,
        expected_amount="1",
        lines=[{"product_id": product.id, "qty": "2", "unit_price": "80.50"}],
    )
    assert res.status_code == 201, res.text
    line = res.json()["lines"][0]
    assert Decimal(line["unit_price"]) == Decimal("80.50")
    assert Decimal(line["line_amount"]) == Decimal("161.00")


def test_f7_a_zero_list_price_leaves_the_line_unpriced(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _unpriced_product(db)
    res = _post(
        client, BASE, customer.id, expected_amount="1", lines=[{"product_id": product.id, "qty": "1"}]
    )
    assert res.status_code == 201, res.text
    line = res.json()["lines"][0]
    assert line["unit_price"] is None
    assert line["line_amount"] is None


def test_f7_negative_unit_price_is_422(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = _post(
        client,
        BASE,
        customer.id,
        expected_amount="1",
        lines=[{"product_id": product.id, "qty": "1", "unit_price": "-1"}],
    )
    assert res.status_code == 422, res.text


def test_f7_expected_amount_left_out_is_the_sum_of_the_lines(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    priced = _product(db)
    unpriced = _unpriced_product(db)
    res = _post(
        client,
        BASE,
        customer.id,
        lines=[
            {"product_id": priced.id, "qty": "2"},
            {"product_id": priced.id, "qty": "1", "unit_price": "40"},
            {"product_id": unpriced.id, "qty": "5"},
        ],
    )
    assert res.status_code == 201, res.text
    assert Decimal(res.json()["expected_amount"]) == Decimal("240.00")


def test_f7_expected_amount_left_out_with_no_lines_is_zero(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    res = _post(client, BASE, customer.id)
    assert res.status_code == 201, res.text
    assert Decimal(res.json()["expected_amount"]) == Decimal("0")


def test_f7_a_typed_expected_amount_wins_over_the_lines(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = _post(
        client, BASE, customer.id, expected_amount="999", lines=[{"product_id": product.id, "qty": "1"}]
    )
    assert res.status_code == 201, res.text
    assert Decimal(res.json()["expected_amount"]) == Decimal("999")


def test_f7_patch_lines_reprices_them(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    created = _post(
        client, BASE, customer.id, expected_amount="1", lines=[{"product_id": product.id, "qty": "1"}]
    ).json()
    res = client.patch(
        f"{BASE}/{created['id']}",
        json={"lines": [{"product_id": product.id, "qty": "4", "unit_price": "25"}]},
    )
    assert res.status_code == 200, res.text
    line = res.json()["lines"][0]
    assert Decimal(line["unit_price"]) == Decimal("25")
    assert Decimal(line["line_amount"]) == Decimal("100.00")


def test_f7_portal_create_prices_lines_and_defaults_the_amount():
    with blank_session() as db:
        _seed(db)
        contact = _contact(db)
        _grant_kind(db, contact.id)
        _portal_agent(db, contact_id=contact.id)
        from app.models.base import company_scope
        from tests.test_sales_opportunities_s2 import _sorento

        with company_scope(db, frozenset({_sorento(db)})):
            product = _product(db)
        with _portal_client(db, contact.id) as c:
            res = _post(
                c,
                PORTAL,
                prospect_name="ZZT Priced Prospect",
                lines=[{"product_id": product.id, "qty": "2"}],
            )
            assert res.status_code == 201, res.text
            body = res.json()
            assert Decimal(body["lines"][0]["unit_price"]) == Decimal("100.00")
            assert Decimal(body["expected_amount"]) == Decimal("200.00")


def test_f7_portal_product_lookup_carries_the_list_price():
    with blank_session() as db:
        contact = _contact(db)
        from app.models.base import company_scope
        from tests.test_sales_opportunities_s2 import _sorento

        with company_scope(db, frozenset({_sorento(db)})):
            priced = _product(db, name="ZZT Lookup Priced")
            unpriced = _unpriced_product(db)
        with _portal_client(db, contact.id) as c:
            res = c.get("/api/v1/public/portal/lookups/products", params={"q": "ZZT", "limit": 50})
            assert res.status_code == 200, res.text
            by_id = {row["product_id"]: row for row in res.json()}
            assert Decimal(by_id[priced.id]["list_price"]) == Decimal("100.00")
            assert by_id[unpriced.id]["list_price"] is None


def test_f7_migration_adds_unit_price_after_the_s2_tables():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "sales_0005_opp_line_price.py"
    spec = importlib.util.spec_from_file_location("sales_0005_opp_line_price", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "sales_0005_opp_line_price"
    assert len(module.revision) <= 32
    assert module.down_revision == "sales_0003_opportunities"

    from app.models.sales import SalesOpportunityLine

    column = SalesOpportunityLine.__table__.c.unit_price
    assert column.nullable is True


def test_f7_an_explicit_null_price_keeps_the_line_unpriced(api):
    # A blank Unit price in the form is sent as null: "no price", not "use the list price"
    # (review of fix round 2), so the saved line matches the amount the screen showed.
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = _post(
        client,
        BASE,
        customer.id,
        expected_amount="1",
        lines=[{"product_id": product.id, "qty": "1", "unit_price": None}],
    )
    assert res.status_code == 201, res.text
    assert res.json()["lines"][0]["unit_price"] is None


def test_f7_patch_with_a_null_amount_takes_the_lines_sum_not_a_500(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    created = _post(client, BASE, customer.id, expected_amount="5").json()
    res = client.patch(
        f"{BASE}/{created['id']}",
        json={"expected_amount": None, "lines": [{"product_id": product.id, "qty": "2"}]},
    )
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["expected_amount"]) == Decimal("200.00")


def test_f7_lines_adding_up_past_what_an_amount_holds_is_422_not_500(api):
    # Security review of fix round 2: qty and price each pass their bounds, but their summed
    # estimate can overflow expected_amount's numeric(15,2).
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = _post(
        client,
        BASE,
        customer.id,
        lines=[{"product_id": product.id, "qty": "9999999999", "unit_price": "9999"}],
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "AMOUNT_TOO_LARGE"
