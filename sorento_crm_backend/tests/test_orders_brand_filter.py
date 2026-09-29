"""Phase 3 fix-round tests - issue #1262 (Samantha case), reviewer finding B3.

`GET /api/v1/order-management/orders` and `.../orders/by-product` already accept
`brand_ids` (`app/api/v1/order_management/orders.py::_narrow_product_ids_by_brand`,
#1262 slice 9, AC-S9-6) - "other order reports" = the orders list / by-product tools
that already take `product_ids`. Reviewer B3: no test proved the NARROWING itself, or
the zero-UUID sentinel (`_narrow_product_ids_by_brand` returns
`["00000000-...-0000"]` rather than falling through to "no filter" when a brand
matches nothing) - disabling either one left every existing test green.

These tests exercise the ROUTE end to end (real Postgres rows, real join through
`Product.brand_id`), not the helper function in isolation, so a regression that
reintroduces either gap is caught at the seam a customer's request actually crosses.

Postgres only (`tests/_pg_fixture.py`), every row seeded here. Modelled on
`tests/test_outstanding_report_brand_filter.py`'s own harness (superadmin client,
`_brand` helper) rather than a second one for the same shape.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.order import Order, OrderLine
from app.models.product import Brand
from app.models.user import User, UserRole, UserRoleAssignment
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._mc_lookup_seed import customer, product, warehouse
from tests._pg_fixture import blank_session, unique_code

ORDERS_BASE = "/api/v1/order-management/orders"
BY_PRODUCT_BASE = "/api/v1/order-management/orders/by-product"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _seed_superadmin(db) -> dict:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('SA')}@test.com", name="ZZT Superadmin", status="ACTIVE")
    role = UserRole(id=str(uuid.uuid4()), slug="superadmin", name="Superadmin")
    db.add_all([user, role])
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()
    return {"id": user.id, "email": user.email}


@pytest.fixture
def client(db):
    principal = _seed_superadmin(db)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _brand(db, *, name: str, code: str) -> Brand:
    row = Brand(id=str(uuid.uuid4()), brand_name=name, brand_code=code, is_active=True, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _order_with_line(db, *, product_id: str, cust_id: str, wh_id: str, order_number: str | None = None) -> Order:
    order = Order(
        id=str(uuid.uuid4()),
        order_number=order_number or unique_code("ORD"),
        customer_id=cust_id,
        is_cancelled=False,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderLine(
            id=str(uuid.uuid4()),
            order_id=order.id,
            product_id=product_id,
            warehouse_id=wh_id,
            quantity=1,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.flush()
    return order


class TestOrdersListBrandFilter:
    def test_brand_ids_narrows_to_that_brands_orders_only(self, client, db):
        sorento_brand = _brand(db, name="Sorento", code="SRT")
        mocha_brand = _brand(db, name="Mocha", code="MCH")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Orders Brand Customer")
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        sorento_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SRTSKU"))
        sorento_product.brand_id = sorento_brand.id
        mocha_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("MCHSKU"))
        mocha_product.brand_id = mocha_brand.id
        db.flush()
        sorento_order = _order_with_line(db, product_id=sorento_product.id, cust_id=cust.id, wh_id=wh.id)
        mocha_order = _order_with_line(db, product_id=mocha_product.id, cust_id=cust.id, wh_id=wh.id)
        db.commit()

        resp = client.get(ORDERS_BASE, params={"brand_ids": [sorento_brand.id]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        order_ids = {row["id"] for row in body["data"]}
        assert sorento_order.id in order_ids, body
        assert mocha_order.id not in order_ids, (
            f"a brand filter must not also return a DIFFERENT brand's order: {body}"
        )

    def test_brand_ids_intersects_with_product_ids(self, client, db):
        sorento_brand = _brand(db, name="Sorento", code="SRT")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Orders Brand Customer 2")
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        product_a = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SRTSKUA"))
        product_a.brand_id = sorento_brand.id
        product_b = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SRTSKUB"))
        product_b.brand_id = sorento_brand.id
        db.flush()
        order_a = _order_with_line(db, product_id=product_a.id, cust_id=cust.id, wh_id=wh.id)
        order_b = _order_with_line(db, product_id=product_b.id, cust_id=cust.id, wh_id=wh.id)
        db.commit()

        # Both products share the SAME brand, but `product_ids` narrows to only one of
        # them - the intersection must keep just that one order, not the brand's whole set.
        resp = client.get(
            ORDERS_BASE, params={"brand_ids": [sorento_brand.id], "product_ids": [product_a.id]}
        )
        assert resp.status_code == 200, resp.text
        order_ids = {row["id"] for row in resp.json()["data"]}
        assert order_ids == {order_a.id}, (
            f"brand_ids + product_ids must be the INTERSECTION, not the brand's whole set: {order_ids!r}"
        )
        assert order_b.id not in order_ids

    def test_brand_with_zero_products_returns_empty_not_every_order(self, client, db):
        empty_brand = _brand(db, name="EmptyBrand", code="EMB")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Orders Brand Customer 3")
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        some_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ANYSKU"))
        db.flush()
        _order_with_line(db, product_id=some_product.id, cust_id=cust.id, wh_id=wh.id)
        db.commit()

        resp = client.get(ORDERS_BASE, params={"brand_ids": [empty_brand.id]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"] == [], (
            f"a brand matching NO products must return an EMPTY result, never fall "
            f"through to 'no filter at all' and return every order: {body}"
        )

    def test_non_uuid_brand_ids_is_rejected(self, client, db):
        resp = client.get(ORDERS_BASE, params={"brand_ids": ["not-a-uuid"]})
        # `parse_uuid_list`'s own convention (`app/services/uuid_list_param.py`) is a
        # 400 `INVALID_UUID`, not FastAPI's default 422 - "rejected", not "silently
        # ignored and every order returned unfiltered", is the actual claim here.
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "INVALID_UUID", resp.text


class TestOrdersByProductBrandFilter:
    def test_brand_with_zero_products_returns_empty_not_every_order(self, client, db):
        empty_brand = _brand(db, name="EmptyBrand2", code="EMB2")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT By-Product Brand Customer")
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        some_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("BYPSKU"))
        db.flush()
        _order_with_line(db, product_id=some_product.id, cust_id=cust.id, wh_id=wh.id)
        db.commit()

        # `product_ids` is a required param for this endpoint (`at least one required`);
        # give it the REAL product so the only thing narrowing it away is the brand.
        resp = client.get(
            BY_PRODUCT_BASE, params={"product_ids": [some_product.id], "brand_ids": [empty_brand.id]}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == [], (
            f"a brand intersecting to nothing must return EMPTY, not the product's "
            f"own unfiltered orders: {resp.json()}"
        )

    def test_non_uuid_brand_ids_is_rejected(self, client, db):
        some_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("BYPSKU2"))
        db.flush()
        db.commit()
        resp = client.get(
            BY_PRODUCT_BASE, params={"product_ids": [some_product.id], "brand_ids": ["not-a-uuid"]}
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "INVALID_UUID", resp.text


class TestN5AnotherCompanysBrand:
    """Fix lane round 2, N5: a brand id from ANOTHER company must give no rows, on
    both orders routes - the brand, its products and its orders are all company
    scoped, and none of them may leak through the brand filter."""

    def test_other_company_brand_gives_no_orders(self, client, db):
        from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        seed_mocha(db)
        mocha_brand = Brand(
            id=str(uuid.uuid4()), brand_name="Mocha", brand_code="MCH", is_active=True, company_id=MOCHA_ID
        )
        db.add(mocha_brand)
        db.flush()
        mocha_cust = customer(db, company_id=MOCHA_ID, name="ZZT Mocha Customer")
        mocha_wh = warehouse(db, company_id=MOCHA_ID)
        mocha_product = product(db, company_id=MOCHA_ID, code=unique_code("MCHX"))
        mocha_product.brand_id = mocha_brand.id
        db.flush()
        order = Order(
            id=str(uuid.uuid4()), order_number=unique_code("ORD"), customer_id=mocha_cust.id,
            is_cancelled=False, company_id=MOCHA_ID,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderLine(
                id=str(uuid.uuid4()), order_id=order.id, product_id=mocha_product.id,
                warehouse_id=mocha_wh.id, quantity=1, company_id=MOCHA_ID,
            )
        )
        db.commit()
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

        resp = client.get(ORDERS_BASE, params={"brand_ids": [mocha_brand.id]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == [], resp.json()

        resp = client.get(BY_PRODUCT_BASE, params={"brand_ids": [mocha_brand.id]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == [], resp.json()


class TestN3BrandNarrowsBySubquery:
    """Fix lane round 2, N3: a brand-only orders call must narrow through a
    `Product.brand_id` subquery, never by reading the brand's whole product id list
    into Python and binding it back as `IN (...)`. Pinned by watching the statements
    the request runs: no product id of the brand is ever a bound parameter."""

    def _bound_values(self, db, call) -> list:
        from sqlalchemy import event

        seen: list = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            if isinstance(parameters, dict):
                seen.extend(str(v) for v in parameters.values())
            elif isinstance(parameters, (list, tuple)):
                for p in parameters:
                    seen.extend(str(v) for v in (p.values() if isinstance(p, dict) else [p]))

        engine = db.get_bind().engine
        event.listen(engine, "before_cursor_execute", _capture)
        try:
            call()
        finally:
            event.remove(engine, "before_cursor_execute", _capture)
        return seen

    def test_brand_only_calls_never_bind_the_brands_product_ids(self, client, db):
        brand = _brand(db, name="Sorento", code="SRT")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT N3 Customer")
        wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
        prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SRTN3"))
        prod.brand_id = brand.id
        db.flush()
        order = _order_with_line(db, product_id=prod.id, cust_id=cust.id, wh_id=wh.id)
        db.commit()

        responses: list = []
        bound = self._bound_values(
            db,
            lambda: responses.extend(
                [
                    client.get(ORDERS_BASE, params={"brand_ids": [brand.id]}),
                    client.get(ORDERS_BASE, params={"brand_ids": [brand.id], "include_summary": "true"}),
                    client.get(BY_PRODUCT_BASE, params={"brand_ids": [brand.id]}),
                ]
            ),
        )
        for resp in responses:
            assert resp.status_code == 200, resp.text
        assert order.id in {row["id"] for row in responses[0].json()["data"]}, responses[0].json()
        assert responses[2].json()["data"], responses[2].json()
        assert prod.id not in bound, "the brand's product ids were bound as a literal IN list"
