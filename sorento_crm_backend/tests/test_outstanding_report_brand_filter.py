"""Phase 2 RED tests - issue #1262 (the Samantha case), GROUP C brand slice, slice 9
(finding F1a), UAC `chatbot-samantha-slices-26sep-acceptance-criteria.md` AC-S9-4.
Round 3 section 6 step 4: `GET /api/v1/order-management/outstanding-report` (and the
underlying `outstanding_report_service.outstanding_report`) take a `brand_ids` filter
(`Product.brand_id`); a brand alone is a valid subject (no `subject_required` 422); the
response names the brand so the chatbot header can say "Brand: Sorento".

Written before `brand_ids` exists on the route/service. Follows
`tests/test_outstanding_report.py`'s own fixtures (`db`/`client`, `_so_line`) rather than
inventing a second harness for the same route.

Postgres only (`tests/_pg_fixture.py`), every row seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Brand
from app.models.user import User, UserRole, UserRoleAssignment
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._mc_lookup_seed import customer, product
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/order-management/outstanding-report"


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


def _brand(db, *, name: str, code: str, company_id: str = DEFAULT_COMPANY_ID) -> Brand:
    row = Brand(id=str(uuid.uuid4()), brand_name=name, brand_code=code, is_active=True, company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _so_line(db, *, product_id, ordered, delivered, customer_id=None, order_date=None, so_number=None):
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=so_number or unique_code("SO"),
        customer_id=customer_id,
        order_date=order_date,
        status="open",
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=product_id,
            qty_ordered=ordered,
            qty_delivered=delivered,
            line_status="open",
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return so


class TestBrandFilterOnTheRoute:
    def test_brand_ids_narrows_the_report_to_that_brands_products(self, client, db):
        sorento_brand = _brand(db, name="Sorento", code="SRT")
        mocha_brand = _brand(db, name="Mocha", code="MCH")
        cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Brand Customer")
        sorento_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SRTSKU"))
        sorento_product.brand_id = sorento_brand.id
        mocha_product = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("MCHSKU"))
        mocha_product.brand_id = mocha_brand.id
        _so_line(db, product_id=sorento_product.id, ordered=10, delivered=3, customer_id=cust.id, order_date=date(2026, 1, 1))
        _so_line(db, product_id=mocha_product.id, ordered=20, delivered=5, customer_id=cust.id, order_date=date(2026, 1, 1))
        db.commit()

        resp = client.get(BASE, params={"brand_ids": [sorento_brand.id], "scope": "so"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (body["so"]["ordered_qty"], body["so"]["outstanding_qty"]) == (10, 7), body

    def test_brand_alone_is_a_valid_subject_no_422(self, client, db):
        sorento_brand = _brand(db, name="Sorento", code="SRT")
        resp = client.get(BASE, params={"brand_ids": [sorento_brand.id], "scope": "so"})
        assert resp.status_code != 422, resp.text
        assert resp.json().get("code") != "subject_required", resp.text

    def test_the_response_echoes_the_brand_name_for_the_header(self, client, db):
        sorento_brand = _brand(db, name="Sorento", code="SRT")
        resp = client.get(BASE, params={"brand_ids": [sorento_brand.id], "scope": "so"})
        assert resp.status_code != 422, resp.text
        body = resp.json()
        assert body.get("brand_name") == "Sorento", body


class TestN5AnotherCompanysBrand:
    """Fix lane round 2, N5: a brand id from ANOTHER company gives no rows and no
    `brand_name` - the header must never name a brand the caller cannot see."""

    def test_other_company_brand_gives_no_rows_and_no_brand_name(self, client, db):
        from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        seed_mocha(db)
        mocha_brand = _brand(db, name="Mocha", code="MCH", company_id=MOCHA_ID)
        mocha_cust = customer(db, company_id=MOCHA_ID, name="ZZT Mocha Brand Customer")
        mocha_product = product(db, company_id=MOCHA_ID, code=unique_code("MCHSKU"))
        mocha_product.brand_id = mocha_brand.id
        so = SalesOrder(
            id=str(uuid.uuid4()), so_number=unique_code("SO"), customer_id=mocha_cust.id,
            order_date=date(2026, 1, 1), status="open", company_id=MOCHA_ID,
        )
        db.add(so)
        db.flush()
        db.add(
            SalesOrderLine(
                id=str(uuid.uuid4()), sales_order_id=so.id, product_id=mocha_product.id,
                qty_ordered=9, qty_delivered=1, line_status="open", company_id=MOCHA_ID,
            )
        )
        db.commit()
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

        resp = client.get(BASE, params={"brand_ids": [mocha_brand.id], "scope": "so"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert not body.get("brand_name"), body
        assert not body["so"]["ordered_qty"], body
