"""AC-B1/B2/B3/B4/B5 for the three incoming-stock tools:
`crm_incoming_stock_list` (IncomingStockService.incoming_list, GET
/api/v1/incoming-stock/list), `crm_incoming_stock_by_product`
(incoming_for_product) and `crm_incoming_stock_shipments` (incoming_shipments,
rows-only company set, no product input per PLAN section 4).

These endpoints return raw dicts, not a `ListResponse` schema (PLAN section 1),
so `lookup_companies` and row `company_name` are plain dict keys - missing
today, which is what every failing assertion below proves.
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
from app.services.incoming_stock_service import IncomingStockService

from tests._mc_lookup_seed import (
    MOCHA_ID,
    inbound_shipment,
    inbound_shipment_line,
    product,
    seed_mocha,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


# =============================================================================
# incoming_list (shipment-rooted)
# =============================================================================


def test_incoming_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    s_mocha = inbound_shipment(db, company_id=MOCHA_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    inbound_shipment_line(db, company_id=MOCHA_ID, shipment_id=s_mocha.id, product_id=p_mocha.id)
    db.commit()

    result = IncomingStockService(db).incoming_list(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {row.get("company_name") for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    for row in result["data"]:
        assert row.get("company_id") in (DEFAULT_COMPANY_ID, MOCHA_ID)
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # No shipment/line seeded for either product.
    db.commit()

    result = IncomingStockService(db).incoming_list(product_ids=[p_sorento.id, p_mocha.id])

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_list_ac_b3_found_in_one_of_several(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    db.commit()

    result = IncomingStockService(db).incoming_list(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert result["data"][0].get("company_name") == "Sorento"
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    db.commit()

    result = IncomingStockService(db).incoming_list(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert result["data"][0].get("company_name") is None
    assert result.get("lookup_companies") is None


def test_incoming_list_ac_b5_rows_span_two_companies_with_no_product_ids(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID, number="ZZT-SHARED-S")
    s_mocha = inbound_shipment(db, company_id=MOCHA_ID, number="ZZT-SHARED-M")
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    inbound_shipment_line(db, company_id=MOCHA_ID, shipment_id=s_mocha.id, product_id=p_mocha.id)
    db.commit()

    result = IncomingStockService(db).incoming_list(query="ZZT-SHARED")

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {row.get("company_name") for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


# --- route level: GET /api/v1/incoming-stock/list -----------------------------


@pytest.fixture
def api():
    with blank_session() as db:
        seed_mocha(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        principal = {"id": str(uuid.uuid4()), "email": "zzt-incoming-list@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        async def _override_scope():
            scope = frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        yield db

        app.dependency_overrides.clear()


def test_incoming_list_route_labels_rows_and_lookup_companies(api):
    db = api
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    s_mocha = inbound_shipment(db, company_id=MOCHA_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    inbound_shipment_line(db, company_id=MOCHA_ID, shipment_id=s_mocha.id, product_id=p_mocha.id)
    db.commit()

    with TestClient(app) as c:
        res = c.get(
            "/api/v1/incoming-stock/list",
            params={"product_ids": [p_sorento.id, p_mocha.id]},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    rows = body["data"]
    assert len(rows) == 2
    names = {row.get("company_name") for row in rows}
    assert names == {"Sorento", "Mocha"}
    assert body.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_list_route_single_company_hit_is_unlabelled(api):
    db = api
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    db.commit()

    with TestClient(app) as c:
        res = c.get(
            "/api/v1/incoming-stock/list",
            params={"product_ids": [p_sorento.id]},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    rows = body["data"]
    assert len(rows) == 1
    assert rows[0].get("company_name") is None
    assert body.get("lookup_companies") is None


# =============================================================================
# incoming_for_product (grouped by product)
# =============================================================================


def test_incoming_by_product_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    s_mocha = inbound_shipment(db, company_id=MOCHA_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    inbound_shipment_line(db, company_id=MOCHA_ID, shipment_id=s_mocha.id, product_id=p_mocha.id)
    db.commit()

    result = IncomingStockService(db).incoming_for_product(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {row.get("company_name") for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_by_product_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    result = IncomingStockService(db).incoming_for_product(
        product_ids=[p_sorento.id, p_mocha.id]
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_by_product_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID)
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    db.commit()

    result = IncomingStockService(db).incoming_for_product(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert result["data"][0].get("company_name") is None
    assert result.get("lookup_companies") is None


# =============================================================================
# incoming_shipments (rows-only company set - no product_ids input at all, so
# AC-B2's "none in several" shape does not apply here: there is no product-id
# axis to span two companies with zero matching rows. See PLAN section 4's
# "no product input" note for this tool. Covered instead: AC-B1 and AC-B4.)
# =============================================================================


def test_incoming_shipments_ac_b1_rows_span_two_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID, number="ZZT-SHIP-SRT")
    s_mocha = inbound_shipment(db, company_id=MOCHA_ID, number="ZZT-SHIP-MCH")
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    inbound_shipment_line(db, company_id=MOCHA_ID, shipment_id=s_mocha.id, product_id=p_mocha.id)
    db.commit()

    result = IncomingStockService(db).incoming_shipments(
        shipment_ids=[s_sorento.id, s_mocha.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {row.get("company_name") for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
        {"id": MOCHA_ID, "name": "Mocha"},
    ]


def test_incoming_shipments_ac_b4_single_company_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    s_sorento = inbound_shipment(db, company_id=DEFAULT_COMPANY_ID, number="ZZT-SHIP-SOLO")
    inbound_shipment_line(db, company_id=DEFAULT_COMPANY_ID, shipment_id=s_sorento.id, product_id=p_sorento.id)
    db.commit()

    result = IncomingStockService(db).incoming_shipments(shipment_ids=[s_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert result["data"][0].get("company_name") is None
    assert result.get("lookup_companies") is None
