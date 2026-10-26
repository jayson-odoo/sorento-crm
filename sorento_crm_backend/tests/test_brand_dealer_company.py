"""Lane BULK-CONTACT-ACCESS (owner ruling 26 Oct 15:20): `brands.dealer_company_id`.

The company whose dealers get this brand from the access-sheet upload (nullable; NULL = a project
brand the upload never gives). Edited through the existing master-data brand API.

Contract:
* POST / PUT accept `dealer_company_id`; the response carries `dealer_company_id` and
  `dealer_company_name`.
* PUT `{"dealer_company_id": null}` clears it; a PUT without the field leaves it alone.
* An unknown company id is a 422 on both POST and PUT.
"""
from __future__ import annotations

import uuid

from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.test_brand_flows_to_purchasing_route import BRANDS_ENDPOINT, api, db  # noqa: F401 - fixtures


def _company(db, code="ZDC"):
    row = Company(id=str(uuid.uuid4()), name="ZZT Dealer Co", code=unique_code(code)[:50])
    db.add(row)
    db.flush()
    return row


def _create(api, name, **extra):
    return api.post(BRANDS_ENDPOINT, json={"brand_code": unique_code("BDC"), "brand_name": name, **extra})


def test_post_with_dealer_company_returns_id_and_name(api, db):
    company = _company(db)
    resp = _create(api, "ZZT Dealer Brand", dealer_company_id=company.id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["dealer_company_id"] == company.id
    assert body["dealer_company_name"] == company.name
    assert api.get(f"{BRANDS_ENDPOINT}/{body['id']}").json()["dealer_company_id"] == company.id


def test_post_without_the_field_is_null(api, db):
    body = _create(api, "ZZT Project Brand").json()
    assert body["dealer_company_id"] is None
    assert body["dealer_company_name"] is None


def test_put_sets_clears_and_leaves_alone(api, db):
    company = _company(db)
    brand_id = _create(api, "ZZT Put Brand").json()["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"dealer_company_id": company.id})
    assert put.status_code == 200, put.text
    assert put.json()["dealer_company_id"] == company.id
    assert put.json()["dealer_company_name"] == company.name

    renamed = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"brand_name": "ZZT Put Brand 2"})
    assert renamed.json()["dealer_company_id"] == company.id

    cleared = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"dealer_company_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["dealer_company_id"] is None
    assert cleared.json()["dealer_company_name"] is None
    assert api.get(f"{BRANDS_ENDPOINT}/{brand_id}").json()["dealer_company_id"] is None


def test_the_list_reads_it_back(api, db):
    company = _company(db)
    brand_id = _create(api, "ZZT Listed Dealer Brand", dealer_company_id=company.id).json()["id"]
    rows = api.get(BRANDS_ENDPOINT, params={"query": "ZZT Listed Dealer Brand"}).json()["data"]
    assert [r["dealer_company_id"] for r in rows if r["id"] == brand_id] == [company.id]


def test_unknown_company_is_422_on_post_and_put(api, db):
    ghost = str(uuid.uuid4())
    assert _create(api, "ZZT Ghost Co Brand", dealer_company_id=ghost).status_code == 422
    brand_id = _create(api, "ZZT Ghost Put Brand").json()["id"]
    assert api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"dealer_company_id": ghost}).status_code == 422
    assert api.get(f"{BRANDS_ENDPOINT}/{brand_id}").json()["dealer_company_id"] is None


def test_the_incumbent_company_is_a_valid_dealer_company(api, db):
    resp = _create(api, "ZZT Srt Dealer Brand", dealer_company_id=DEFAULT_COMPANY_ID)
    assert resp.status_code == 201, resp.text
    assert resp.json()["dealer_company_id"] == DEFAULT_COMPANY_ID


def test_a_malformed_company_id_is_422_without_database_text(api, db):
    from fastapi.testclient import TestClient

    from app.main import app

    tc = TestClient(app, raise_server_exceptions=False)
    resp = tc.post(BRANDS_ENDPOINT, json={"brand_code": unique_code("BDC"), "brand_name": "ZZT Bad Id", "dealer_company_id": "x"})
    assert resp.status_code == 422, resp.text[:300]
    low = resp.text.lower()
    assert "select " not in low and "psycopg" not in low and "sqlalchemy" not in low

    brand_id = _create(api, "ZZT Bad Id Put").json()["id"]
    put = tc.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"dealer_company_id": "x"})
    assert put.status_code == 422, put.text[:300]
    low = put.text.lower()
    assert "select " not in low and "psycopg" not in low and "sqlalchemy" not in low
