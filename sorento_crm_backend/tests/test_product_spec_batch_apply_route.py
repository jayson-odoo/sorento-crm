"""`POST .../by-product/{product_id}/values/batch` - one batch call over
`apply_spec_values`, atomic (AC-B.9).

PR 4 contract: `documentation/plans/master-data/PLAN-spec-authoring-verification.md`
("PR 4 implementation contract"). The route does not exist yet, so every request
below 404s today - that IS the expected red state.

Fixture/dependency-override pattern copied from
tests/test_product_specifications_routes.py, matching
tests/test_product_spec_extract_route.py's `api` fixture.

One ambiguity, stated rather than guessed past: the contract says atomicity runs
"through the choke point's own validation" (`apply_spec_values`'s `_prepare`, which
checks `op`/blank-value but does NOT check a spec_key against the registry at all -
see `app/services/product_spec_write.py::_prepare`). An "unknown spec_key" entry can
therefore only be rejected by the ROUTE doing its own registry lookup first, mirroring
`PUT .../values/{spec_key}`'s existing `if row is None: raise handle_not_found(...)`.
The exact status code for that case is left unpinned (`in (400, 404)`) because both
are legitimate for "the choke point's own validation" reading two different ways;
what IS pinned is that nothing gets written for ANY entry in the batch.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.product_class_signal import backfill_category_signals
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/master-data/product-specifications"
_USER = {"id": str(uuid.uuid4()), "email": "spec-batch@zzt.test"}

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-BA-KS", category_name="ZZT-BA-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-BA-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-BA-SRT", brand_name="Sorento")
        second = Company(id=str(uuid.uuid4()), name="ZZT BA Second Co", code="ZZT-BA2")
        s.add_all([cat, uom, brand, second])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})
        yield s


def _product(db, code: str, description: str = "SORENTO CERAMIC KITCHEN SINK") -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
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


def _batch(client, product_id: str, entries: list[dict]):
    return client.post(
        f"{ENDPOINT}/by-product/{product_id}/values/batch", json={"entries": entries}
    )


def _spec_for(db, code: str) -> ProductSpecifications | None:
    return (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .first()
    )


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def test_batch_denies_without_the_edit_permission(api, db):
    client, _allow = api
    _registry_key(db, "material", allowed_values=["brass"])
    product = _product(db, "ZZT-BA-DENY")
    db.commit()

    response = _batch(client, product.id, [{"spec_key": "material", "value": "brass", "evidence": "x"}])

    assert response.status_code == 403


def test_batch_401s_without_a_principal(api, db):
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass"])
    product = _product(db, "ZZT-BA-401")
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user_or_api_key] = _deny
    try:
        response = _batch(client, product.id, [{"spec_key": "material", "value": "brass", "evidence": "x"}])
    finally:
        app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# happy path (AC-B.9)
# --------------------------------------------------------------------------- #
def test_batch_happy_path_writes_all_three_entries_through_one_call(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    _registry_key(db, "finish", allowed_values=["chrome", "black"])
    _registry_key(db, "trap_type", allowed_values=["s_trap", "p_trap"])
    # A description that states NO material: the default fixture says CERAMIC, which
    # derivation reads, so writing material=brass by hand would raise a real
    # `human_override_conflict` and land the row on `needs_review` (correctly - a
    # disagreement between the master and the flyer is the thing D8 exists to surface).
    # This test is about the batch write, so the fixture is kept clear of that.
    product = _product(db, "ZZT-BA-HAPPY", "SORENTO KITCHEN SINK ZZT-BA-HAPPY")
    db.commit()

    calls = []
    import app.services.product_spec_write as write_module

    real_apply = write_module.apply_spec_values

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(write_module, "apply_spec_values", _spy)

    response = _batch(
        client,
        product.id,
        [
            {"spec_key": "material", "value": "brass", "evidence": "Brass Body"},
            {"spec_key": "finish", "value": "chrome", "evidence": "Chrome Finish"},
            {"spec_key": "trap_type", "value": "s_trap", "evidence": "S-Trap"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_code"] == "ZZT-BA-HAPPY"
    assert body["rows_written"] == 1
    assert set(body["spec_keys"]) == {"material", "finish", "trap_type"}

    assert len(calls) == 1, "must write through exactly one apply_spec_values call"

    spec = _spec_for(db, "ZZT-BA-HAPPY")
    assert spec.values["material"]["value"] == "brass"
    assert spec.provenance["material"]["source"] == "human"
    assert spec.provenance["material"]["evidence"] == "read from text: Brass Body"
    assert spec.status == "authored"


def test_batch_atomic_a_bad_entry_writes_nothing(api, db):
    """A blank value 400s through `_prepare` before any DB write happens."""
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass"])
    _registry_key(db, "finish", allowed_values=["chrome"])
    product = _product(db, "ZZT-BA-ATOMIC-BLANK")
    db.commit()

    response = _batch(
        client,
        product.id,
        [
            {"spec_key": "material", "value": "brass", "evidence": "Brass Body"},
            {"spec_key": "finish", "value": "   ", "evidence": "Blank"},
        ],
    )

    assert response.status_code == 400, response.text
    spec = _spec_for(db, "ZZT-BA-ATOMIC-BLANK")
    assert spec is None or "material" not in (spec.values or {})


def test_batch_atomic_an_unknown_spec_key_writes_nothing(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass"])
    product = _product(db, "ZZT-BA-ATOMIC-UNKKEY")
    db.commit()

    response = _batch(
        client,
        product.id,
        [
            {"spec_key": "material", "value": "brass", "evidence": "Brass Body"},
            {"spec_key": "not_a_real_spec_key", "value": "x", "evidence": "y"},
        ],
    )

    assert response.status_code in (400, 404), response.text
    spec = _spec_for(db, "ZZT-BA-ATOMIC-UNKKEY")
    assert spec is None or "material" not in (spec.values or {})


def test_batch_rejects_an_empty_entry_list(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    product = _product(db, "ZZT-BA-EMPTY")
    db.commit()

    response = _batch(client, product.id, [])

    assert response.status_code == 422, response.text


def test_batch_rejects_fifty_one_entries(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    for i in range(51):
        _registry_key(db, f"zzt_key_{i}", data_type="text")
    product = _product(db, "ZZT-BA-TOOMANY")
    db.commit()

    entries = [
        {"spec_key": f"zzt_key_{i}", "value": "x", "evidence": "y"} for i in range(51)
    ]
    response = _batch(client, product.id, entries)

    assert response.status_code == 422, response.text


def test_batch_accepts_fifty_entries(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    for i in range(50):
        _registry_key(db, f"zzt_key_{i}", data_type="text")
    product = _product(db, "ZZT-BA-MAXCOUNT")
    db.commit()

    entries = [
        {"spec_key": f"zzt_key_{i}", "value": "x", "evidence": "y"} for i in range(50)
    ]
    response = _batch(client, product.id, entries)

    assert response.status_code == 200, response.text
    assert response.json()["rows_written"] == 1


# --------------------------------------------------------------------------- #
# BLOCKER - the batch route must validate against the registry like the single
# PUT `.../values/{spec_key}` does (data_type coercion, merged-allowed-values check,
# registry-forced unit). Today it only checks the spec_key EXISTS (see the pre-flight
# comment above `set_spec_values_in_one_batch`) and hands the raw value straight to
# `apply_spec_values`, which itself does no registry validation at all
# (`product_spec_write._prepare` only checks op / blank-value / source) - so an out-of
# -vocabulary enum value, a non-numeric "numeric" value, an arbitrary caller unit and
# an un-coerced boolean spelling all currently WRITE, unchanged, straight to the row.
#
# The PUT route's own violations 400 (`_spec_reject`, see
# test_put_rejects_a_non_number_for_a_numeric_key /
# test_put_rejects_an_empty_string_for_a_free_text_key in
# tests/test_product_specifications_routes.py). The batch route is asked to answer
# 422 for these two instead - a body that named a value the registry cannot accept is
# the wrong SHAPE for this call, not merely a bad business state - so these are
# deliberately NOT copy-pasted onto the PUT route's 400.
# --------------------------------------------------------------------------- #
def test_batch_rejects_an_enum_value_outside_the_merged_vocabulary(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    product = _product(db, "ZZT-BA-ENUMBAD")
    db.commit()

    response = _batch(
        client, product.id, [{"spec_key": "material", "value": "plastic", "evidence": "x"}]
    )

    assert response.status_code == 422, response.text
    message = response.json().get("message", "")
    assert message, "must carry a readable message, not a bare status"
    assert "material" in message.lower() or "plastic" in message.lower()

    spec = _spec_for(db, "ZZT-BA-ENUMBAD")
    assert spec is None or "material" not in (spec.values or {})


def test_batch_rejects_a_non_numeric_value_for_a_numeric_key(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "trap_length", data_type="numeric", unit="mm")
    product = _product(db, "ZZT-BA-NUMBAD")
    db.commit()

    response = _batch(
        client,
        product.id,
        [{"spec_key": "trap_length", "value": "not-a-number", "evidence": "x"}],
    )

    assert response.status_code == 422, response.text
    assert response.json().get("message")

    spec = _spec_for(db, "ZZT-BA-NUMBAD")
    assert spec is None or "trap_length" not in (spec.values or {})


def test_batch_atomic_a_registry_violation_writes_nothing_from_the_whole_batch(api, db):
    """The same atomicity guarantee the existing atomic tests pin, for a REGISTRY
    violation rather than a blank value or an unknown key: one bad entry must still
    take the other, otherwise-valid entries down with it."""
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "material", allowed_values=["brass", "ceramic"])
    _registry_key(db, "finish", allowed_values=["chrome", "black"])
    product = _product(db, "ZZT-BA-ATOMIC-ENUM")
    db.commit()

    response = _batch(
        client,
        product.id,
        [
            {"spec_key": "material", "value": "brass", "evidence": "Brass Body"},
            {"spec_key": "finish", "value": "polka_dot", "evidence": "Not a real finish"},
        ],
    )

    assert response.status_code == 422, response.text
    spec = _spec_for(db, "ZZT-BA-ATOMIC-ENUM")
    assert spec is None or "material" not in (spec.values or {})


def test_batch_ignores_the_callers_unit_and_stores_the_registrys_own_unit(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "trap_length", data_type="numeric", unit="mm")
    product = _product(db, "ZZT-BA-UNIT")
    db.commit()

    response = _batch(
        client,
        product.id,
        [{"spec_key": "trap_length", "value": 250, "unit": "cm", "evidence": "S-Trap 250"}],
    )

    assert response.status_code == 200, response.text
    spec = _spec_for(db, "ZZT-BA-UNIT")
    assert spec.values["trap_length"]["value"] == 250
    assert spec.values["trap_length"]["unit"] == "mm", (
        "the REGISTRY's unit must win - the caller cannot smuggle in a different one"
    )


@pytest.mark.parametrize("spelling", ["true", "Yes", "1", "TRUE"])
def test_batch_accepts_the_same_truthy_boolean_spellings_the_put_route_accepts(
    api, db, spelling
):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "has_drainer", data_type="boolean")
    product = _product(db, f"ZZT-BA-BOOL-{spelling.upper()}")
    db.commit()

    response = _batch(
        client,
        product.id,
        [{"spec_key": "has_drainer", "value": spelling, "evidence": "Drainer board"}],
    )

    assert response.status_code == 200, response.text
    spec = _spec_for(db, f"ZZT-BA-BOOL-{spelling.upper()}")
    assert spec.values["has_drainer"]["value"] is True


def test_batch_coerces_a_non_truthy_boolean_spelling_to_false(api, db):
    client, allow = api
    allow.add("master_data.products.edit")
    _registry_key(db, "has_drainer", data_type="boolean")
    product = _product(db, "ZZT-BA-BOOL-FALSE")
    db.commit()

    response = _batch(
        client,
        product.id,
        [{"spec_key": "has_drainer", "value": "no", "evidence": "No drainer"}],
    )

    assert response.status_code == 200, response.text
    spec = _spec_for(db, "ZZT-BA-BOOL-FALSE")
    assert spec.values["has_drainer"]["value"] is False
