"""AC-B1/B2/B3/B4/B5 for `crm_inventory_stock_balance_list` (StockService.list_stock,
GET /api/v1/inventory/stock/balance).

Modelled on tests/test_attachment_company_stamp_in_list.py: blank_session, a
seeded Mocha company, a pinned two-company scope, own data chain per test.
Postgres only.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.inventory_service import StockService

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, stock, warehouse
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


# --- AC-B1: found in several -------------------------------------------------


def test_ac_b1_found_in_both_companies_labels_every_row_and_lookup_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_mocha = warehouse(db, company_id=MOCHA_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    stock(db, company_id=MOCHA_ID, product_id=p_mocha.id, warehouse_id=wh_mocha.id)
    db.commit()

    result = StockService(db).list_stock(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    for row in result["data"]:
        assert row.company_id in (DEFAULT_COMPANY_ID, MOCHA_ID)
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


# --- AC-B2: none in several ---------------------------------------------------


def test_ac_b2_none_in_either_company_still_names_both_in_lookup_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # No Stock rows seeded for either product at all.
    db.commit()

    result = StockService(db).list_stock(product_ids=[p_sorento.id, p_mocha.id])

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


# --- AC-B3: found in one of several -------------------------------------------


def test_ac_b3_found_in_one_of_several_still_names_both(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    # Mocha product has no stock row at all.
    db.commit()

    result = StockService(db).list_stock(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) == "Sorento"
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


# --- AC-B4: single-company lookup under a two-company caller scope -----------


def test_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    db.commit()

    result = StockService(db).list_stock(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None


# --- AC-B5: rows span two companies with NO product_ids given ----------------


def test_ac_b5_rows_span_two_companies_with_no_product_ids_filter(db):
    """A free-text / unfiltered listing whose returned page happens to span two
    companies is labelled exactly like AC-B1, even though no product_ids were
    passed in."""
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_mocha = warehouse(db, company_id=MOCHA_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    stock(db, company_id=MOCHA_ID, product_id=p_mocha.id, warehouse_id=wh_mocha.id)
    db.commit()

    result = StockService(db).list_stock(warehouse_ids=[wh_sorento.id, wh_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


# --- route level: GET /api/v1/inventory/stock/balance -------------------------


@pytest.fixture
def api():
    with blank_session() as db:
        seed_mocha(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        principal = {"id": str(uuid.uuid4()), "email": "zzt-stock-balance@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        async def _override_scope():
            scope = frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        yield db

        app.dependency_overrides.clear()


def test_route_labels_rows_and_lookup_companies_for_a_two_company_hit(api):
    db = api
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_mocha = warehouse(db, company_id=MOCHA_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    stock(db, company_id=MOCHA_ID, product_id=p_mocha.id, warehouse_id=wh_mocha.id)
    db.commit()

    with TestClient(app) as c:
        res = c.get(
            "/api/v1/inventory/stock/balance",
            params={"product_ids": [p_sorento.id, p_mocha.id]},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    rows = body["data"]
    assert len(rows) == 2
    names = {row.get("company_name") for row in rows}
    assert names == {"Sorento", "Mocha"}
    assert body.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_route_single_company_hit_is_byte_identical_shape(api):
    db = api
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    wh_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p_sorento.id, warehouse_id=wh_sorento.id)
    db.commit()

    with TestClient(app) as c:
        res = c.get(
            "/api/v1/inventory/stock/balance",
            params={"product_ids": [p_sorento.id]},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    rows = body["data"]
    assert len(rows) == 1
    assert rows[0].get("company_name") is None
    assert body.get("lookup_companies") is None
