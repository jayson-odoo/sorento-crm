"""A1 - product specs as a ranked list (AC-901, AC-902).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.product_service import ProductService
from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session
from app.services.company_scope import DEFAULT_COMPANY_ID


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _registry(db, *, key, label, unit=None, rank_weight=1.0, data_type="numeric"):
    row = ProductSpecRegistry(
        id=str(uuid.uuid4()),
        spec_key=key,
        label=label,
        data_type=data_type,
        unit=unit,
        rank_weight=rank_weight,
    )
    db.add(row)
    db.flush()
    return row


def _spec_row(db, *, product_id, values):
    row = ProductSpecifications(
        id=str(uuid.uuid4()),
        product_id=product_id,
        values=values,
    )
    db.add(row)
    db.flush()
    return row


def test_spec_list_only_populated_keys_ordered_by_rank_weight(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _registry(db, key="wattage", label="Wattage", unit="W", rank_weight=3.0)
    _registry(db, key="thickness", label="Thickness", unit="mm", rank_weight=5.0)
    _registry(db, key="unused_key", label="Unused", rank_weight=9.0)  # never derived
    _spec_row(
        db,
        product_id=prod.id,
        values={
            "wattage": {"value": 60},
            "thickness": {"value": 1.2, "unit": "mm"},
        },
    )
    db.commit()

    specs = ProductService(db).spec_list_for_products([prod.id])[prod.id]
    assert [s["key"] for s in specs] == ["thickness", "wattage"]  # rank_weight desc
    assert specs[0] == {
        "key": "thickness", "label": "Thickness", "value": 1.2, "unit": "mm", "rank_weight": 5.0,
    }
    assert specs[1] == {
        "key": "wattage", "label": "Wattage", "value": 60, "unit": "W", "rank_weight": 3.0,
    }


def test_spec_list_empty_for_product_with_no_derived_row(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="NOSPEC")
    db.commit()
    assert ProductService(db).spec_list_for_products([prod.id]) == {}


def test_spec_list_falls_back_to_registry_unit_when_value_carries_none(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _registry(db, key="diameter", label="Diameter", unit="mm", rank_weight=1.0)
    _spec_row(db, product_id=prod.id, values={"diameter": {"value": 407}})
    db.commit()

    specs = ProductService(db).spec_list_for_products([prod.id])[prod.id]
    assert specs[0]["unit"] == "mm"


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app  # noqa: E402
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-product-specs@test.com"}
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


def test_route_include_specs_returns_ranked_list(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _registry(db, key="wattage", label="Wattage", unit="W", rank_weight=3.0)
    _spec_row(db, product_id=prod.id, values={"wattage": {"value": 60}})
    db.commit()

    resp = client.get(
        "/api/v1/master-data/products/",
        params={"product_ids": prod.id, "include_specs": "true"},
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()["data"][0]
    assert row["specs"] == [
        {"key": "wattage", "label": "Wattage", "value": 60, "unit": "W", "rank_weight": 3.0}
    ]


def test_route_no_include_specs_key_absent(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    db.commit()

    resp = client.get("/api/v1/master-data/products/", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    assert "specs" not in resp.json()["data"][0]


def test_route_both_include_specifications_and_include_specs(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _registry(db, key="wattage", label="Wattage", unit="W", rank_weight=3.0)
    _spec_row(db, product_id=prod.id, values={"wattage": {"value": 60}})
    db.commit()

    resp = client.get(
        "/api/v1/master-data/products/",
        params={"product_ids": prod.id, "include_specs": "true", "include_specifications": "true"},
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()["data"][0]
    assert row["specs"][0]["key"] == "wattage"
    assert row["specifications"]["values"]["wattage"] == 60
