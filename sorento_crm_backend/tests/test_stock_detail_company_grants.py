"""`GET /project-sales/fulfilment-planning/stock-detail` with `company_scope=grants`.

An order inquiry filed in company A can carry a line at a warehouse owned by company B, when
the user holds both and picked that bin through a `company_scope=grants` picker. With A
active, the stock-detail read looked the bin up under A alone and answered 404. The optional
`company_scope=grants` widens the read to the caller's grants (the same helper
`inventory/warehouses.py` uses), never beyond them, and never for an integration caller.

Postgres, blank scratch schema, every row seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  MUST be first app import (circular import in guards)
from app.models.base import company_scope
from app.models.company import Company, UserCompany
from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_user

URL = "/api/v1/project-sales/fulfilment-planning/stock-detail"
#: The incumbent company every test schema is seeded with (tests/conftest.py).
COMPANY_A = "00000000-0000-0000-0000-000000000001"
MARKER = "zzt-stock-detail-grants"


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db) -> str:
    suffix = uuid.uuid4().hex[:8]
    row = Company(id=_uid(), name=f"ZZT Other Co {suffix}", code=f"Z{suffix}")
    db.add(row)
    db.flush()
    return str(row.id)


def _grant(db, user_id: str, company_id: str) -> None:
    db.add(UserCompany(id=_uid(), user_id=user_id, company_id=company_id))
    db.flush()


def _product(db) -> Product:
    uom = UnitOfMeasure(
        id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit", company_id=COMPANY_A
    )
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat",
        company_id=COMPANY_A,
    )
    db.add_all([uom, category])
    db.flush()
    code = f"ZZT-{_uid()[:6]}"
    row = Product(
        id=_uid(), product_code=code, product_name=f"{MARKER} {code}",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
        company_id=COMPANY_A,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, company_id: str) -> Warehouse:
    code = f"ZZT{_uid()[:4]}"
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project", fulfilment_planning=True, company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, *, on_hand: int) -> None:
    db.add(
        Stock(
            id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
            quantity_on_hand=on_hand, quantity_reserved=0, company_id=warehouse.company_id,
        )
    )
    db.flush()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        # Company A is active, as the session resolver would stamp it for the request.
        with company_scope(db, frozenset({COMPANY_A})):
            company_b = _company(db)
            granted = seed_user(db, contact_pk=None, slugs=("projects.projects.view",))
            _grant(db, granted, COMPANY_A)
            _grant(db, granted, company_b)
            ungranted = seed_user(db, contact_pk=None, slugs=("projects.projects.view",))
            _grant(db, ungranted, COMPANY_A)

            product = _product(db)
            # Company B's bin: seeded under B so the insert auto-stamp agrees with the row.
            with company_scope(db, frozenset({company_b})):
                bin_b = _warehouse(db, company_b)
                _stock(db, product, bin_b, on_hand=7)

            who = {"user": {"id": granted, "email": "a@zzt.test", "auth_method": "password"}}

            def _db():
                yield db

            def _user():
                return who["user"]

            app.dependency_overrides[get_db] = _db
            app.dependency_overrides[get_current_user] = _user
            app.dependency_overrides[get_current_user_or_api_key] = _user
            app.dependency_overrides[apply_company_scope] = lambda: frozenset({COMPANY_A})
            try:
                with TestClient(app) as c:
                    yield type(
                        "Api",
                        (),
                        {
                            "c": c, "db": db, "who": who, "granted": granted,
                            "ungranted": ungranted, "product": product, "bin_b": bin_b,
                        },
                    )
            finally:
                app.dependency_overrides.clear()


def _params(api, **extra) -> dict:
    return {"product_id": str(api.product.id), "warehouse_id": str(api.bin_b.id), **extra}


def test_grants_reads_a_granted_companys_bin(api):
    res = api.c.get(URL, params=_params(api, company_scope="grants"))

    assert res.status_code == 200, res.text
    assert Decimal(str(res.json()["qty_on_hand"])) == Decimal("7"), res.json()


def test_without_company_scope_the_other_companys_bin_is_still_404(api):
    res = api.c.get(URL, params=_params(api))

    assert res.status_code == 404, res.text


def test_grants_never_reaches_a_company_the_user_is_not_granted(api):
    api.who["user"] = {"id": api.ungranted, "email": "b@zzt.test", "auth_method": "password"}

    res = api.c.get(URL, params=_params(api, company_scope="grants"))

    assert res.status_code == 404, res.text


def test_an_integration_caller_is_not_widened(api):
    api.who["user"] = {
        "id": api.granted, "email": "a@zzt.test", "auth_method": "integration_api_key",
    }

    res = api.c.get(
        URL, params=_params(api, company_scope="grants"), headers={"X-API-Key": "zzt-fake-key"}
    )

    assert res.status_code == 404, res.text


def test_an_unknown_company_scope_value_is_refused(api):
    res = api.c.get(URL, params=_params(api, company_scope="everything"))

    assert res.status_code == 422, res.text


def test_a_group_read_is_never_widened(api):
    """Security review: grants applies to one bin; a whole ownership group or the pools is
    refused rather than read across companies."""
    res = api.c.get(
        URL,
        params={"product_id": str(api.product.id), "group": "pools", "company_scope": "grants"},
    )

    assert res.status_code == 422, res.text
    assert res.json()["code"] == "stock_detail_scope_group", res.json()


def test_the_active_scope_is_restored_after_a_grants_read(api):
    from app.models.base import get_company_scope

    res = api.c.get(URL, params=_params(api, company_scope="grants"))

    assert res.status_code == 200, res.text
    assert get_company_scope(api.db) == frozenset({COMPANY_A})
