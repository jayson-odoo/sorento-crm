"""The first pytest coverage `app/api/v1/master_data/product_specifications.py` has
ever had (confirmed by grep before writing this file - zero prior test references).

PUT/DELETE `.../by-product/{product_id}/values/{spec_key}` reduce, per PR1-CONTRACT.md
section 6, to validation plus one call into `app.services.product_spec_write.
apply_spec_values`. The route's product lookup, registry lookup, boolean/numeric
coercion and merged-allowed-values check are UNCHANGED - only the write block moves.

Dependency-override pattern copied from tests/test_ai_prompt_registry.py:359-396
(overrides get_db / get_current_user / get_current_user_or_api_key, monkeypatches
UserPermissionService.check_user_has_permission against an `allow` set of granted
slugs). The route reads `current_user.get("email")` for the evidence string, so the
fake user carries one.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.product_class_signal import backfill_category_signals
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/master-data/product-specifications"
_USER = {"id": str(uuid.uuid4()), "email": "spec-writer@zzt.test"}

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-RT-KS", category_name="ZZT-RT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-RT-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-RT-SRT", brand_name="SORENTO")
        second = Company(id=str(uuid.uuid4()), name="ZZT RT Second Co", code="ZZT-RT2")
        s.add_all([cat, uom, brand, second])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})
        yield s


def _product(db, code: str, *, company_id=None) -> Product:
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


def _registry_key(db, key: str, *, data_type="enum", allowed_values=None, unit=None) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        spec_key=key,
        label=key.replace("_", " ").title(),
        data_type=data_type,
        allowed_values=allowed_values or [],
        unit=unit,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    # All-companies scope, same as test_product_spec_registry.py's client fixture:
    # the route-level company-scope resolver is a separate concern from the
    # permission gate under test here, and these tests seed a second company on
    # purpose (AC-F.4 fan-out) so the request must be able to see both copies.
    app.dependency_overrides[apply_company_scope] = lambda: None
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
# PUT .../values/{spec_key}
# --------------------------------------------------------------------------- #
def test_put_happy_path_stores_the_value_response_contract_and_fans_out(api, db):
    """AC-F.4 - the response contract is unchanged, but the value now reaches every
    company copy of the code, not just the row named in the URL."""
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    with company_scope(db, None):
        product = _product(db, "ZZT-RT-PUT-1")
        _product(db, "ZZT-RT-PUT-1", company_id=_REFS["company2"])
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/material",
        json={"value": "brass"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"spec_key": "material", "value": "brass", "source": "human"}

    with company_scope(db, None):
        specs = (
            db.query(ProductSpecifications)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .filter(Product.product_code == "ZZT-RT-PUT-1")
            .all()
        )
        assert len(specs) == 2, "both company copies must have a spec row"
        assert all(s.values["material"]["value"] == "brass" for s in specs)
        assert all(s.provenance["material"]["source"] == "human" for s in specs)


def test_put_denies_without_the_edit_permission(api, db):
    client, _allow = api  # nothing granted
    _registry_key(db, "material", allowed_values=["brass"])
    product = _product(db, "ZZT-RT-PUT-DENY")
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/material",
        json={"value": "brass"},
    )

    assert response.status_code == 403


def test_put_rejects_a_non_number_for_a_numeric_key(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "diameter", data_type="numeric", unit="mm")
    product = _product(db, "ZZT-RT-PUT-NUM")
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/diameter",
        json={"value": "not-a-number"},
    )

    assert response.status_code == 400, response.text


def test_put_404s_for_an_unknown_spec_key(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    product = _product(db, "ZZT-RT-PUT-UNKKEY")
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/not_a_real_spec_key",
        json={"value": "x"},
    )

    assert response.status_code == 404


def test_put_rejects_an_empty_string_for_a_free_text_key(api, db):
    """6b.5 - an empty free-text value is rejected with a readable message pointing
    at the remove action: stored, it canonicalises to nothing while derivation keeps
    producing something, which would raise the same conflict on every run forever."""
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "notes", data_type="text")  # no allowed_values - free text
    product = _product(db, "ZZT-RT-PUT-EMPTY")
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/notes",
        json={"value": "   "},
    )

    assert response.status_code == 400, response.text
    # AppException's body IS exc.detail directly (app/main.py's app_exception_handler
    # returns JSONResponse(content=exc.detail)), not wrapped in a further "detail" key.
    message = response.json()["message"].lower()
    assert "blank" in message, message


def test_put_404s_for_an_unknown_product(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass"])
    db.commit()

    response = client.put(
        f"{ENDPOINT}/by-product/{uuid.uuid4()}/values/material",
        json={"value": "brass"},
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# DELETE .../values/{spec_key}
# --------------------------------------------------------------------------- #
def test_delete_with_no_mode_reverts_and_keeps_the_shipped_response_contract(api, db):
    """The shipped frontend sends no `mode` parameter at all and depends on exactly
    this shape - this must stay true after the `mode` parameter is added."""
    from app.services.product_spec_derivation import derive_for_code

    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    product = _product(db, "ZZT-RT-DEL-1")
    db.commit()
    derive_for_code(db, "ZZT-RT-DEL-1", commit=True)

    put_response = client.put(
        f"{ENDPOINT}/by-product/{product.id}/values/material",
        json={"value": "brass"},
    )
    assert put_response.status_code == 200, put_response.text

    response = client.delete(f"{ENDPOINT}/by-product/{product.id}/values/material")

    assert response.status_code == 200, response.text
    assert response.json() == {"spec_key": "material", "cleared": True, "mode": "revert"}

    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    assert spec.values["material"]["value"] == "ceramic", "reverted to what derivation reads"


def test_delete_mode_absent_writes_a_tombstone_that_survives_a_re_derive(api, db):
    from app.services.product_spec_derivation import derive_for_code

    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    product = _product(db, "ZZT-RT-DEL-2")
    db.commit()
    derive_for_code(db, "ZZT-RT-DEL-2", commit=True)

    response = client.delete(
        f"{ENDPOINT}/by-product/{product.id}/values/material", params={"mode": "absent"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"spec_key": "material", "cleared": True, "mode": "absent"}

    derive_for_code(db, "ZZT-RT-DEL-2", commit=True)
    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    assert "material" not in spec.values
    assert spec.provenance["material"].get("absent") is True


def test_delete_rejects_an_invalid_mode(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass"])
    product = _product(db, "ZZT-RT-DEL-3")
    db.commit()

    response = client.delete(
        f"{ENDPOINT}/by-product/{product.id}/values/material", params={"mode": "nonsense"}
    )

    # `_spec_reject` is the only path an invalid mode can reach - it always raises a
    # 400 AppException, never a 422 - so pin the reachable one rather than accepting
    # either.
    assert response.status_code == 400, response.text


def test_delete_mode_absent_404s_for_a_spec_key_the_registry_does_not_define(api, db):
    """6b.6 - mode=absent pins `status='authored'` on every copy of the code for good,
    so the key it names must be one the registry knows, or a typo writes a permanent
    provenance entry no registry-driven screen will ever show."""
    client, allow = api
    allow.add("master_data.products.edit")
    product = _product(db, "ZZT-RT-DEL-ABSENT-UNKNOWN")
    db.commit()

    response = client.delete(
        f"{ENDPOINT}/by-product/{product.id}/values/not_a_real_spec_key",
        params={"mode": "absent"},
    )

    assert response.status_code == 404, response.text


def test_delete_mode_revert_succeeds_for_a_stored_key_the_registry_no_longer_defines(api, db):
    """6b.6 - the deliberate asymmetry: mode=revert is NOT checked against the
    registry, because a key the registry has since dropped is still stored on the
    row and handing it back to derivation must stay possible. This is the one most
    likely to be "tidied" away later into a symmetric check with mode=absent."""
    from app.models.base import company_scope
    from app.services.product_spec_write import apply_spec_values

    client, allow = api
    allow.add("master_data.products.edit")
    product = _product(db, "ZZT-RT-DEL-REVERT-UNKNOWN")
    db.commit()

    # Hand-write a value under a key the registry never defines, mirroring a key the
    # registry dropped after a row already carried it.
    with company_scope(db, None):
        apply_spec_values(
            db,
            "ZZT-RT-DEL-REVERT-UNKNOWN",
            [
                {
                    "spec_key": "legacy_key_not_in_registry",
                    "op": "set",
                    "value": "x",
                    "source": "human",
                }
            ],
        )
    db.commit()

    response = client.delete(
        f"{ENDPOINT}/by-product/{product.id}/values/legacy_key_not_in_registry",
        params={"mode": "revert"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "spec_key": "legacy_key_not_in_registry",
        "cleared": True,
        "mode": "revert",
    }


def test_delete_denies_without_the_edit_permission(api, db):
    client, _allow = api  # nothing granted
    product = _product(db, "ZZT-RT-DEL-DENY")
    db.commit()

    response = client.delete(f"{ENDPOINT}/by-product/{product.id}/values/material")

    assert response.status_code == 403
