"""RED-phase pytest for the verification ROUTES (PR 3, UAC group D): every route
appended to `app/api/v1/master_data/product_specifications.py` under
`/verification/*`, same router / module guard, plus `GET /by-product/{id}` gaining
`verification` (a VerificationBlock) and `values_hash` (AC-D.14).

Paths, bodies, status codes and outcome strings are pinned by the orchestrator
contract note (`pr3-contract.md`, "API contract" + "Routes"). Neither
`app.services.product_spec_verification` nor the new routes exist yet, so this file
fails at collection today (ImportError) - that IS the expected red state.

`api` fixture copied verbatim (dependency-override pattern) from
`tests/test_product_specifications_routes.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecException
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services import product_spec_verification as psv
from tests._pg_fixture import blank_session, unique_code

ENDPOINT = "/api/v1/master-data/product-specifications"
_USER = {"id": str(uuid.uuid4()), "email": "verify-router@zzt.test", "name": "Route Verifier"}
VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-VR-KS", category_name="ZZT-VR-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-VR-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-VR-SRT", brand_name="SORENTO")
        second = Company(id=str(uuid.uuid4()), name="ZZT VR Second Co", code="ZZT-VR2")
        s.add_all([cat, uom, brand, second])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})
        yield s


def _product(db, code: str, *, company_id: str | None = None) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="SORENTO CERAMIC KITCHEN SINK",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER

    # All-companies scope for the whole request: several tests here seed a second
    # company on purpose (the by-product cross-copy test) and the request must be
    # able to see both copies.
    #
    # The `lambda: None` in test_product_specifications_routes.py is NOT enough on its
    # own - it only skips the resolver, and the session keeps the suite-wide Sorento
    # default that conftest's `after_begin` listener stamps, so the second company's
    # copy 404s. Stamp the scope the way the real dependency does, so the cross-copy
    # test exercises AC-D.14 rather than the company filter.
    def _all_companies_scope():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
        app.dependency_overrides.pop(apply_company_scope, None)


# --------------------------------------------------------------------------- #
# GET /verification/worklist
# --------------------------------------------------------------------------- #
def test_get_worklist_happy_path(api, db):
    client, allow = api
    allow.add(VIEW)
    code = unique_code("VR-WL")
    _product(db, code)
    db.commit()

    response = client.get(f"{ENDPOINT}/verification/worklist")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"data", "pagination", "summary"}
    row = next(r for r in body["data"] if r["product_code"] == code)
    assert row["verification"]["state"] == "unverified"
    assert "values_hash" in row
    assert {"have", "applicable"} <= set(row["coverage"])
    assert "open_exceptions" in row


def test_get_worklist_carries_the_class_facet(api, db):
    """The class filter's options ride the worklist response - no second endpoint."""
    client, allow = api
    allow.add(VIEW)
    code = unique_code("VR-WLCLASS")
    _product(db, code)
    db.commit()

    body = client.get(f"{ENDPOINT}/verification/worklist", params={"query": code}).json()

    assert "classes" in body
    assert all(isinstance(label, str) for label in body["classes"])
    assert body["classes"] == sorted(set(body["classes"]))


def test_get_worklist_denies_without_the_view_permission(api, db):
    client, _allow = api

    response = client.get(f"{ENDPOINT}/verification/worklist")

    assert response.status_code == 403


def test_get_worklist_422s_on_an_invalid_page(api, db):
    client, allow = api
    allow.add(VIEW)

    response = client.get(f"{ENDPOINT}/verification/worklist", params={"page": 0})

    assert response.status_code == 422, response.text


def test_get_worklist_422s_on_an_unknown_state(api, db):
    client, allow = api
    allow.add(VIEW)

    response = client.get(f"{ENDPOINT}/verification/worklist", params={"state": "sort_of_verified"})

    assert response.status_code == 422, response.text


def test_get_worklist_422s_on_an_unknown_sort(api, db):
    client, allow = api
    allow.add(VIEW)

    response = client.get(f"{ENDPOINT}/verification/worklist", params={"sort": "brand"})

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# POST /verification/verify
# --------------------------------------------------------------------------- #
def test_verify_happy_path(api, db):
    client, allow = api
    allow.add(EDIT)
    code = unique_code("VR-VFY")
    _product(db, code)
    db.commit()
    derive_for_code(db, code, commit=True)
    current_hash = psv.current_values_hash(db, code)

    response = client.post(
        f"{ENDPOINT}/verification/verify",
        json={"product_code": code, "values_hash": current_hash},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "verified"
    assert body["product_code"] == code
    assert body["values_hash"] == current_hash
    assert body["verification"]["state"] == "verified"


def test_verify_denies_without_the_edit_permission(api, db):
    client, _allow = api

    response = client.post(
        f"{ENDPOINT}/verification/verify",
        json={"product_code": unique_code("VR-VFY-DENY"), "values_hash": "x"},
    )

    assert response.status_code == 403


def test_verify_422s_when_values_hash_is_missing(api, db):
    client, allow = api
    allow.add(EDIT)

    response = client.post(
        f"{ENDPOINT}/verification/verify",
        json={"product_code": unique_code("VR-VFY-BAD")},
    )

    assert response.status_code == 422


def test_verify_409s_with_values_changed_and_the_current_hash(api, db):
    client, allow = api
    allow.add(EDIT)
    code = unique_code("VR-VFY-STALE")
    _product(db, code)
    db.commit()
    derive_for_code(db, code, commit=True)
    current_hash = psv.current_values_hash(db, code)

    response = client.post(
        f"{ENDPOINT}/verification/verify",
        json={"product_code": code, "values_hash": "0" * 64},
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "values_changed"
    assert body["values_hash"] == current_hash


def test_verify_409s_with_exceptions_open(api, db):
    client, allow = api
    allow.add(EDIT)
    code = unique_code("VR-VFY-EXC")
    _product(db, code)
    db.commit()
    derive_for_code(db, code, commit=True)
    current_hash = psv.current_values_hash(db, code)
    db.add(
        ProductSpecException(
            id=str(uuid.uuid4()), product_code=code, spec_key="material", reason="human_override_conflict"
        )
    )
    db.commit()

    response = client.post(
        f"{ENDPOINT}/verification/verify",
        json={"product_code": code, "values_hash": current_hash},
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "exceptions_open"
    assert body["exceptions"]


# --------------------------------------------------------------------------- #
# POST /verification/verify-bulk
# --------------------------------------------------------------------------- #
def test_verify_bulk_happy_path_mixed_outcomes(api, db):
    client, allow = api
    allow.add(EDIT)
    ok_code = unique_code("VR-BULK-OK")
    bad_code = unique_code("VR-BULK-BAD")
    _product(db, ok_code)
    _product(db, bad_code)
    db.commit()
    derive_for_code(db, ok_code, commit=True)
    derive_for_code(db, bad_code, commit=True)
    good_hash = psv.current_values_hash(db, ok_code)

    response = client.post(
        f"{ENDPOINT}/verification/verify-bulk",
        json={
            "items": [
                {"product_code": ok_code, "values_hash": good_hash},
                {"product_code": bad_code, "values_hash": "0" * 64},
            ]
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    outcomes = {r["product_code"]: r["outcome"] for r in body["results"]}
    assert outcomes[ok_code] == "verified"
    assert outcomes[bad_code] == "values_changed"
    assert body["counts"]["verified"] == 1
    assert body["counts"]["skipped"] == 1


def test_verify_bulk_denies_without_the_edit_permission(api, db):
    client, _allow = api

    response = client.post(
        f"{ENDPOINT}/verification/verify-bulk",
        json={"items": [{"product_code": "x", "values_hash": "y"}]},
    )

    assert response.status_code == 403


def test_verify_bulk_422s_on_an_empty_items_list(api, db):
    client, allow = api
    allow.add(EDIT)

    response = client.post(f"{ENDPOINT}/verification/verify-bulk", json={"items": []})

    assert response.status_code == 422


def test_verify_bulk_422s_over_500_items(api, db):
    client, allow = api
    allow.add(EDIT)
    items = [{"product_code": f"ZZT-VR-BULK-{i}", "values_hash": "x"} for i in range(501)]

    response = client.post(f"{ENDPOINT}/verification/verify-bulk", json={"items": items})

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /verification/unverify
# --------------------------------------------------------------------------- #
def test_unverify_happy_path(api, db):
    client, allow = api
    allow.add(EDIT)
    code = unique_code("VR-UNV")
    _product(db, code)
    db.commit()
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    verify_resp = client.post(
        f"{ENDPOINT}/verification/verify", json={"product_code": code, "values_hash": h}
    )
    assert verify_resp.status_code == 200, verify_resp.text

    response = client.post(f"{ENDPOINT}/verification/unverify", json={"product_code": code})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "unverified"
    assert body["verification"]["state"] == "unverified"


def test_unverify_denies_without_the_edit_permission(api, db):
    client, _allow = api

    response = client.post(
        f"{ENDPOINT}/verification/unverify", json={"product_code": unique_code("VR-UNV-DENY")}
    )

    assert response.status_code == 403


def test_unverify_422s_when_product_code_is_missing(api, db):
    client, allow = api
    allow.add(EDIT)

    response = client.post(f"{ENDPOINT}/verification/unverify", json={})

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /verification/unverify-bulk
# --------------------------------------------------------------------------- #
def test_unverify_bulk_happy_path_mixed_outcomes(api, db):
    client, allow = api
    allow.add(EDIT)
    verified_code = unique_code("VR-UBULK-V")
    unverified_code = unique_code("VR-UBULK-U")
    _product(db, verified_code)
    _product(db, unverified_code)
    db.commit()
    derive_for_code(db, verified_code, commit=True)
    h = psv.current_values_hash(db, verified_code)
    verify_resp = client.post(
        f"{ENDPOINT}/verification/verify", json={"product_code": verified_code, "values_hash": h}
    )
    assert verify_resp.status_code == 200, verify_resp.text

    response = client.post(
        f"{ENDPOINT}/verification/unverify-bulk",
        json={"product_codes": [verified_code, unverified_code]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    outcomes = {r["product_code"]: r["outcome"] for r in body["results"]}
    assert outcomes[verified_code] == "unverified"
    assert outcomes[unverified_code] == "no_change"
    assert body["counts"]["unverified"] == 1
    assert body["counts"]["no_change"] == 1


def test_unverify_bulk_denies_without_the_edit_permission(api, db):
    client, _allow = api

    response = client.post(f"{ENDPOINT}/verification/unverify-bulk", json={"product_codes": ["x"]})

    assert response.status_code == 403


def test_unverify_bulk_422s_on_an_empty_product_codes_list(api, db):
    client, allow = api
    allow.add(EDIT)

    response = client.post(f"{ENDPOINT}/verification/unverify-bulk", json={"product_codes": []})

    assert response.status_code == 422


def test_unverify_bulk_422s_over_500_codes(api, db):
    client, allow = api
    allow.add(EDIT)
    codes = [f"ZZT-VR-UBULK-{i}" for i in range(501)]

    response = client.post(f"{ENDPOINT}/verification/unverify-bulk", json={"product_codes": codes})

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# GET /by-product/{id} gains verification + values_hash (AC-D.14)
# --------------------------------------------------------------------------- #
def test_by_product_carries_verification_block_and_values_hash(api, db):
    client, allow = api
    allow.add(VIEW)
    code = unique_code("VR-BYPROD")
    product = _product(db, code)
    db.commit()
    derive_for_code(db, code, commit=True)

    response = client.get(f"{ENDPOINT}/by-product/{product.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verification"]["state"] == "unverified"
    assert "values_hash" in body


def test_by_product_shows_the_identical_verification_block_on_both_company_copies(api, db):
    client, allow = api
    allow.add(VIEW)
    allow.add(EDIT)
    code = unique_code("VR-XCOPY")
    with company_scope(db, None):
        p1 = _product(db, code)
        p2 = _product(db, code, company_id=_REFS["company2"])
        db.commit()
        derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    verify_resp = client.post(
        f"{ENDPOINT}/verification/verify", json={"product_code": code, "values_hash": h}
    )
    assert verify_resp.status_code == 200, verify_resp.text

    body1 = client.get(f"{ENDPOINT}/by-product/{p1.id}").json()
    body2 = client.get(f"{ENDPOINT}/by-product/{p2.id}").json()

    assert body1["verification"] == body2["verification"]
    assert body1["values_hash"] == body2["values_hash"]
