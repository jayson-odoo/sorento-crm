"""`POST .../by-product/{product_id}/extract` - proposals only, never a write
(AC-B.1, B.2, B.3, B.4, B.5).

PR 4 contract: `documentation/plans/master-data/PLAN-spec-authoring-verification.md`
("PR 4 implementation contract"). The route does not exist yet, so every request
below 404s today - that IS the expected red state.

Dependency-override pattern copied from tests/test_product_specifications_routes.py
(`api` fixture: overrides get_db / get_current_user / get_current_user_or_api_key /
apply_company_scope, monkeypatches UserPermissionService.check_user_has_permission
against an `allow` set). Registry seeded with `seed_spec_registry` (same shipped
tables `product_spec_derivation.py` ships), matching tests/test_product_spec_
understanding.py, so both the deterministic rule pass and the model-path vocabulary
validation run against real, curated tokens rather than invented ones.

Two assumptions stated up front, because the contract does not spell out either
mechanically and both are load-bearing for how these tests are built:

  1. The route passes the DB-configured rules/scopes into `propose_from_text`
     (mirroring `derive_for_code`'s own default), not the hardcoded shipped tables
     directly. This is untestable as a distinct behaviour here because
     `seed_spec_registry` seeds a FRESH `ProductSpecRegistry` row's
     `derivation_rules` at `[]` (empty - `configured_rules` then falls back to the
     shipped table for that key), so the two are identical after a real seed. Every
     rule-pass assertion below is written against real shipped tokens for exactly
     this reason - it holds whichever way the coder wires it.
  2. The out-of-class-key drop (AC-B.4) is exercised using the PRODUCT'S OWN stored
     class (from a `derive_for_code` run against a real description), not a class
     `propose_from_text` invents from the pasted text - `propose_from_text` alone has
     no product description to read a class out of, so the route must be the one
     consulting the product's real, already-derived class.

The model-path monkeypatches `product_spec_understanding._resolve_provider`, the
exact technique tests/test_product_spec_understanding.py uses for "no model" and "a
model answer" - the tester brief names that file for this reason.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductFlyerText, ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_write import apply_spec_values
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/master-data/product-specifications"
_USER = {"id": str(uuid.uuid4()), "email": "spec-extractor@zzt.test"}

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-EX-KS", category_name="ZZT-EX-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-EX-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-EX-SRT", brand_name="Sorento")
        second = Company(id=str(uuid.uuid4()), name="ZZT EX Second Co", code="ZZT-EX2")
        s.add_all([cat, uom, brand, second])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})
        seed_spec_registry(s, commit=False)
        s.flush()
        yield s


def _product(db, code: str, description: str) -> Product:
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


def _extract(client, product_id: str, text: str):
    return client.post(f"{ENDPOINT}/by-product/{product_id}/extract", json={"text": text})


def _by_key(body: dict) -> dict[str, dict]:
    return {p["spec_key"]: p for p in body["proposals"]}


def _no_model(monkeypatch):
    import app.services.product_spec_understanding as understanding

    monkeypatch.setattr(understanding, "_resolve_provider", lambda db: (None, "openai", ""))


def _model_returning(payload: dict, monkeypatch):
    import app.services.product_spec_understanding as understanding

    result = SimpleNamespace(
        content=json.dumps(payload), prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    provider = SimpleNamespace(chat=lambda *a, **k: result)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (provider, "openai", "gpt-test")
    )


def _model_raising(monkeypatch):
    import app.services.product_spec_understanding as understanding

    def _boom(*a, **k):
        raise RuntimeError("simulated provider failure")

    provider = SimpleNamespace(chat=_boom)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (provider, "openai", "gpt-test")
    )


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def test_extract_denies_without_the_edit_permission(api, db, monkeypatch):
    client, _allow = api
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-DENY", "SORENTO CERAMIC BASIN ZZT-EX-DENY")
    db.commit()

    response = _extract(client, product.id, "Brass Body")

    assert response.status_code == 403


def test_extract_401s_without_a_principal(api, db, monkeypatch):
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from fastapi import HTTPException

    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-401", "SORENTO CERAMIC BASIN ZZT-EX-401")
    db.commit()

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user_or_api_key] = _deny
    try:
        response = _extract(client, product.id, "Brass Body")
    finally:
        app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# validation (AC-B.2)
# --------------------------------------------------------------------------- #
def test_extract_rejects_blank_text(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-BLANK", "SORENTO CERAMIC BASIN ZZT-EX-BLANK")
    db.commit()

    response = _extract(client, product.id, "   ")

    assert response.status_code == 422, response.text


def test_extract_rejects_text_over_8000_characters(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-LONG", "SORENTO CERAMIC BASIN ZZT-EX-LONG")
    db.commit()

    response = _extract(client, product.id, "x" * 8001)

    assert response.status_code == 422, response.text


def test_extract_accepts_text_at_exactly_8000_characters(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-MAXLEN", "SORENTO CERAMIC BASIN ZZT-EX-MAXLEN")
    db.commit()

    response = _extract(client, product.id, "x" * 8000)

    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# no write (AC-B.1, B.2)
# --------------------------------------------------------------------------- #
def test_extract_writes_nothing(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-NOWRITE", "SORENTO ONE PIECE WC ZZT-EX-NOWRITE")
    db.commit()
    derive_for_code(db, "ZZT-EX-NOWRITE", commit=True)

    before_flyer_count = db.query(ProductFlyerText).count()
    before = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-NOWRITE")
        .first()
    )
    before_snapshot = (dict(before.values), dict(before.provenance), before.updated_at)

    response = _extract(client, product.id, "Solid Brass Body. *PP Seat Cover")
    assert response.status_code == 200, response.text

    db.expire_all()
    after = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-NOWRITE")
        .first()
    )
    after_snapshot = (dict(after.values), dict(after.provenance), after.updated_at)

    assert after_snapshot == before_snapshot
    assert db.query(ProductFlyerText).count() == before_flyer_count


# --------------------------------------------------------------------------- #
# response contract
# --------------------------------------------------------------------------- #
def test_extract_happy_path_with_a_model_returns_semantic_engine(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _model_returning(
        {"specs": [{"key": "trap_type", "value": "s_trap", "evidence": "S-Trap"}]}, monkeypatch
    )
    product = _product(db, "ZZT-EX-SEMANTIC", "SORENTO ONE PIECE WC ZZT-EX-SEMANTIC")
    db.commit()
    derive_for_code(db, "ZZT-EX-SEMANTIC", commit=True)

    response = _extract(client, product.id, "A washdown WC with an S-trap outlet")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_code"] == "ZZT-EX-SEMANTIC"
    assert body["engine"] == "semantic"
    assert body["model"] == "gpt-test"
    proposal = _by_key(body)["trap_type"]
    assert proposal["value"] == "s_trap"
    assert proposal["kind"] == "new"
    assert proposal["data_type"] == "enum"
    assert proposal["label"]
    assert proposal["evidence"]


def test_extract_with_no_model_reachable_degrades_to_deterministic(api, db, monkeypatch):
    """AC-B.5 - 200, not 502, and the rule-pass proposals still come through."""
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-DETERM", "SORENTO ONE PIECE WC ZZT-EX-DETERM")
    db.commit()
    derive_for_code(db, "ZZT-EX-DETERM", commit=True)

    response = _extract(client, product.id, "Washdown. S-Trap outlet 250mm")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine"] == "deterministic"
    assert body["model"] is None
    proposal = _by_key(body)["trap_type"]
    assert proposal["value"] == "s_trap"
    assert proposal["evidence"] == "S-TRAP"


def test_extract_when_the_provider_raises_also_degrades_to_deterministic(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _model_raising(monkeypatch)
    product = _product(db, "ZZT-EX-PROVFAIL", "SORENTO ONE PIECE WC ZZT-EX-PROVFAIL")
    db.commit()
    derive_for_code(db, "ZZT-EX-PROVFAIL", commit=True)

    response = _extract(client, product.id, "Washdown. S-Trap outlet 250mm")

    assert response.status_code == 200, response.text
    assert response.json()["engine"] == "deterministic"


# --------------------------------------------------------------------------- #
# AC-B.4 - never invented vocabulary, never an out-of-class key
# --------------------------------------------------------------------------- #
def test_extract_drops_an_unknown_key_the_model_invents(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _model_returning(
        {"specs": [{"key": "levitation", "value": "yes"}, {"key": "trap_type", "value": "p_trap"}]},
        monkeypatch,
    )
    product = _product(db, "ZZT-EX-INVENT-KEY", "SORENTO ONE PIECE WC ZZT-EX-INVENT-KEY")
    db.commit()
    derive_for_code(db, "ZZT-EX-INVENT-KEY", commit=True)

    response = _extract(client, product.id, "A floating toilet")

    assert response.status_code == 200, response.text
    by_key = _by_key(response.json())
    assert "levitation" not in by_key
    assert by_key["trap_type"]["value"] == "p_trap"


def test_extract_drops_a_value_outside_the_enum_vocabulary(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _model_returning(
        {"specs": [{"key": "trap_type", "value": "x_trap"}]},
        monkeypatch,
    )
    product = _product(db, "ZZT-EX-INVENT-VAL", "SORENTO ONE PIECE WC ZZT-EX-INVENT-VAL")
    db.commit()
    derive_for_code(db, "ZZT-EX-INVENT-VAL", commit=True)

    response = _extract(client, product.id, "A toilet with an x-trap")

    assert response.status_code == 200, response.text
    assert "trap_type" not in _by_key(response.json())


def test_extract_drops_a_class_scoped_key_the_product_is_the_wrong_class_for(api, db, monkeypatch):
    """seat_material only applies to Water Closet; this product derives to Tap."""
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-WRONGCLASS", "SORENTO BASIN TAP ZZT-EX-WRONGCLASS")
    db.commit()
    derive_for_code(db, "ZZT-EX-WRONGCLASS", commit=True)

    response = _extract(client, product.id, "Washdown With Rimless. *PP Seat Cover")

    assert response.status_code == 200, response.text
    assert "seat_material" not in _by_key(response.json())


def test_extract_keeps_a_class_scoped_key_for_the_right_class(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-RIGHTCLASS", "SORENTO ONE PIECE WC ZZT-EX-RIGHTCLASS")
    db.commit()
    derive_for_code(db, "ZZT-EX-RIGHTCLASS", commit=True)

    response = _extract(client, product.id, "Washdown With Rimless. *PP Seat Cover")

    assert response.status_code == 200, response.text
    assert _by_key(response.json())["seat_material"]["value"] == "pp"


# --------------------------------------------------------------------------- #
# AC-B.3 - kind computation, server-side
# --------------------------------------------------------------------------- #
def test_kind_new_when_the_stored_key_is_absent(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-KIND-NEW", "SORENTO ONE PIECE WC ZZT-EX-KIND-NEW")
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-NEW", commit=True)

    response = _extract(client, product.id, "Washdown. S-Trap outlet 250mm")

    proposal = _by_key(response.json())["trap_type"]
    assert proposal["kind"] == "new"
    assert proposal["stored_value"] is None


def test_kind_omitted_and_counted_in_unchanged_when_equal_after_coercion(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(
        db, "ZZT-EX-KIND-SAME", "SORENTO ONE PIECE WC (700X400X800MM) ZZT-EX-KIND-SAME"
    )
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-SAME", commit=True)

    response = _extract(client, product.id, "Washdown. H800mm")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "dim_height" not in _by_key(body)
    assert body["unchanged"] >= 1


def test_kind_conflict_when_the_stored_value_is_authored_by_a_person(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-KIND-HUMAN", "SORENTO ONE PIECE WC ZZT-EX-KIND-HUMAN")
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-HUMAN", commit=True)
    apply_spec_values(
        db,
        "ZZT-EX-KIND-HUMAN",
        [{"spec_key": "seat_material", "op": "set", "value": "uf", "source": "human"}],
        actor=_USER,
    )

    response = _extract(client, product.id, "*PP Seat Cover")

    proposal = _by_key(response.json())["seat_material"]
    assert proposal["kind"] == "conflict"
    assert proposal["stored_value"] == "uf"
    assert proposal["stored_source"] == "human"


def test_kind_conflict_for_a_tombstoned_key(api, db, monkeypatch):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-KIND-TOMB", "SORENTO ONE PIECE WC ZZT-EX-KIND-TOMB")
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-TOMB", commit=True)
    apply_spec_values(
        db,
        "ZZT-EX-KIND-TOMB",
        [{"spec_key": "seat_material", "op": "absent", "source": "human"}],
        actor=_USER,
    )

    response = _extract(client, product.id, "*PP Seat Cover")

    proposal = _by_key(response.json())["seat_material"]
    assert proposal["kind"] == "conflict"


def test_kind_change_when_the_stored_derived_value_differs(api, db, monkeypatch):
    """finish is not in `_DESCRIPTION_FIRST_KEYS`, so a derived, differing value is a
    plain `change`, not a `conflict`."""
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-KIND-CHANGE-BL", "SORENTO CERAMIC ART BASIN ONLY")
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-CHANGE-BL", commit=True)
    stored = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-KIND-CHANGE-BL")
        .first()
    )
    assert stored.values["finish"]["value"] == "black"
    assert stored.provenance["finish"]["source"] == "derived"

    response = _extract(client, product.id, "Chrome finish")

    proposal = _by_key(response.json())["finish"]
    assert proposal["value"] == "chrome"
    assert proposal["kind"] == "change"
    assert proposal["stored_value"] == "black"


def test_kind_conflict_for_a_description_first_key_stored_derived(api, db, monkeypatch):
    """dim_length is in `_DESCRIPTION_FIRST_KEYS`: a stored, derived value is a
    `conflict`, not a plain `change` - the lifted "description beats the flyer for
    sizes" rule, expressed as default-unticked instead of applied silently."""
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(
        db, "ZZT-EX-KIND-DESCFIRST", "SORENTO ONE PIECE WC (700X400X800MM) ZZT-EX-KIND-DESCFIRST"
    )
    db.commit()
    derive_for_code(db, "ZZT-EX-KIND-DESCFIRST", commit=True)

    response = _extract(client, product.id, "Washdown. D: L680xW375xH770mm")

    proposal = _by_key(response.json())["dim_length"]
    assert proposal["value"] == 680
    assert proposal["kind"] == "conflict"
    assert proposal["stored_value"] == 700
