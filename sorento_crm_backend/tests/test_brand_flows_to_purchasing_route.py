"""Brand CRUD route + `flows_to_purchasing` (PLAN-brand-flows-to-purchasing.md, AC-2, AC-3).

RED for Phase 2: `BrandCreate`/`BrandUpdate`/`BrandResponse` carry no `flows_to_purchasing`
field yet, and the column does not exist on `brands` - every test below fails against
TODAY's code with a validation error, an AttributeError, or a response missing the field.

Contract this file drives:

* POST /api/v1/master-data/brands without the field creates a brand with
  `flows_to_purchasing: true` in the response.
* POST with `flows_to_purchasing: false` stores and returns false.
* PUT /api/v1/master-data/brands/{id} with `{"flows_to_purchasing": false}` persists it;
  GET list and GET by id read it back. PUT without the field leaves it alone.

Fixtures modelled on `tests/scm/test_local_buy_routing_toggle.py`'s `api` fixture
(`get_current_user` override + a monkeypatched `check_user_has_permission`) since brand
create/update go through `require_permission`, not the API-key-tolerant variant the select
endpoint uses.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.base import set_company_scope
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, unique_code

BRANDS_ENDPOINT = "/api/v1/master-data/brands"
VIEW_PERMISSION = "master_data.brands.view"
ADD_PERMISSION = "master_data.brands.add"
EDIT_PERMISSION = "master_data.brands.edit"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    allow = {VIEW_PERMISSION, ADD_PERMISSION, EDIT_PERMISSION}

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    caller = {"id": _u(), "email": f"{unique_code('zztbftp')}@zzt.test"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def test_post_without_the_field_defaults_true(api, db):
    resp = api.post(
        BRANDS_ENDPOINT,
        json={"brand_code": unique_code("BFTP"), "brand_name": "ZZT No Field Brand"},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["flows_to_purchasing"] is True


def test_post_with_false_stores_and_returns_false(api, db):
    resp = api.post(
        BRANDS_ENDPOINT,
        json={
            "brand_code": unique_code("BFTP"),
            "brand_name": "ZZT Blocked Brand",
            "flows_to_purchasing": False,
        },
    )

    assert resp.status_code == 201
    assert resp.json()["flows_to_purchasing"] is False


def test_put_false_persists_and_get_reads_it_back(api, db):
    create = api.post(
        BRANDS_ENDPOINT,
        json={"brand_code": unique_code("BFTP"), "brand_name": "ZZT Put Brand"},
    )
    assert create.status_code == 201
    brand_id = create.json()["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"flows_to_purchasing": False})
    assert put.status_code == 200
    assert put.json()["flows_to_purchasing"] is False

    got = api.get(f"{BRANDS_ENDPOINT}/{brand_id}")
    assert got.status_code == 200
    assert got.json()["flows_to_purchasing"] is False

    listed = api.get(BRANDS_ENDPOINT, params={"query": "ZZT Put Brand"})
    assert listed.status_code == 200
    rows = [r for r in listed.json()["data"] if r["id"] == brand_id]
    assert rows and rows[0]["flows_to_purchasing"] is False


def test_put_without_the_field_leaves_it_alone(api, db):
    create = api.post(
        BRANDS_ENDPOINT,
        json={
            "brand_code": unique_code("BFTP"),
            "brand_name": "ZZT Untouched Brand",
            "flows_to_purchasing": False,
        },
    )
    assert create.status_code == 201
    brand_id = create.json()["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"brand_name": "ZZT Renamed Brand"})
    assert put.status_code == 200
    assert put.json()["flows_to_purchasing"] is False
