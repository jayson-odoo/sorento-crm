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
model answer" - the tester brief names that file for this reason. The stubs take
`*_agent` because `_resolve_provider` now takes the agent name it is resolving for
(the last test in this file is what asks for that); `understand_phrase` still calls it
with the session alone, which is why the sibling file's one-argument stubs still hold.
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

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db, *_agent: (None, "openai", "")
    )


def _model_returning(payload: dict, monkeypatch):
    import app.services.product_spec_understanding as understanding

    result = SimpleNamespace(
        content=json.dumps(payload), prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    provider = SimpleNamespace(chat=lambda *a, **k: result)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db, *_agent: (provider, "openai", "gpt-test")
    )


def _model_raising(monkeypatch):
    import app.services.product_spec_understanding as understanding

    def _boom(*a, **k):
        raise RuntimeError("simulated provider failure")

    provider = SimpleNamespace(chat=_boom)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db, *_agent: (provider, "openai", "gpt-test")
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


# --------------------------------------------------------------------------- #
# multi-value `finish` must survive as ONE proposal, not be silently dropped.
#
# `propose_from_text` already turns "ROSE GOLD + MATT BLACK" into
# `finish: ["rose_gold", "black"]` - proven directly against `product_spec_derivation.
# propose_from_text` and against a normal `derive_for_code` run over the SAME text in
# the description (both store the list; see the module docstring's MULTI_VALUE_KEYS).
# But `extract_spec_proposals` re-validates every rule-pass hit through
# `product_spec_understanding._validated_pairs` -> `_coerce`, which only ever
# `str()`s a scalar - `str(["rose_gold", "black"])` matches nothing in the enum's
# allowed values, so `_coerce` returns None and the whole proposal is dropped on the
# floor. The text said something real about the product and the review screen never
# shows it.
# --------------------------------------------------------------------------- #
def test_extract_reports_a_multi_value_finish_as_one_proposal_carrying_the_list(
    api, db, monkeypatch
):
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(db, "ZZT-EX-MULTIFINISH", "SORENTO ONE PIECE WC ZZT-EX-MULTIFINISH")
    db.commit()
    derive_for_code(db, "ZZT-EX-MULTIFINISH", commit=True)

    response = _extract(client, product.id, "ROSE GOLD + MATT BLACK")

    assert response.status_code == 200, response.text
    by_key = _by_key(response.json())
    assert "finish" in by_key, "a real, two-tone finish must not be silently dropped"
    proposal = by_key["finish"]
    assert proposal["value"] == ["rose_gold", "black"]
    assert proposal["kind"] == "new"


def test_applying_a_multi_value_finish_proposal_stores_what_derivation_would_store(
    api, db, monkeypatch
):
    """A normal `derive_for_code` over a description naming two finishes stores
    `finish: {"value": ["rose_gold", "black"]}` (proven directly against `derive_for_
    code` - see the module docstring above). Accepting the SAME reading through the
    extract-then-batch-apply path must store the identical shape, not a stringified
    version of it and not nothing at all."""
    client, allow = api
    allow.add("master_data.products.edit")
    product = _product(db, "ZZT-EX-MULTIFINISH-APPLY", "SORENTO ONE PIECE WC ZZT-EX-MULTIFINISH-APPLY")
    db.commit()
    derive_for_code(db, "ZZT-EX-MULTIFINISH-APPLY", commit=True)

    response = client.post(
        f"{ENDPOINT}/by-product/{product.id}/values/batch",
        json={
            "entries": [
                {
                    "spec_key": "finish",
                    "value": ["rose_gold", "black"],
                    "evidence": "ROSE GOLD + MATT BLACK",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    stored = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-MULTIFINISH-APPLY")
        .first()
    )
    db.expire_all()
    assert stored.values["finish"]["value"] == ["rose_gold", "black"], (
        "the batch write must store the SAME list shape derivation stores, not a "
        "stringified value and not a dropped key"
    )


# --------------------------------------------------------------------------- #
# BLOCKER - scope gate: a proposed value for a GATE key (e.g. `class`) must not
# override the product's OWN stored gate value when deciding whether a different
# proposed key is in scope.
#
# `_in_scope` builds its gate by starting from `stored_values` and then, for EVERY
# candidate including one proposing the gate key itself, doing
# `gate.values[entry["key"]] = {"value": entry["value"]}` UNCONDITIONALLY - so a
# candidate that proposes `class` overwrites the product's real, derived class before
# `_apply_scope` ever runs. `bowl_count` (`applies_when: {"class": ["Kitchen
# Sink"]}`, product_spec_registry.py) is the sharpest case: a Water Closet's pasted
# text that ALSO gets read as naming "Kitchen Sink" must not smuggle a bowl_count
# proposal past its own gate on the strength of its own candidate class.
# --------------------------------------------------------------------------- #
def test_in_scope_gates_on_the_products_stored_class_not_a_candidates_own_proposed_class():
    """Direct unit test of `_in_scope`'s gate accumulator - no DB, no model, matching
    the shape of `test_apply_scope_*` in tests/test_product_spec_propose_from_text.py,
    which exercises the shared `_apply_scope` the same way through a different
    accumulator."""
    from app.services.product_spec_extract import _in_scope
    from app.services.product_spec_registry import shipped_scopes

    candidates = [
        {"key": "class", "value": "Kitchen Sink"},
        {"key": "bowl_count", "value": 2},
    ]
    stored_values = {"class": {"value": "Water Closet"}}
    stored_provenance = {
        "class": {"source": "derived", "confidence": 1.0, "evidence": "TOILET"}
    }

    kept = _in_scope(candidates, stored_values, stored_provenance, shipped_scopes())

    kept_keys = {entry["key"] for entry in kept}
    assert "bowl_count" not in kept_keys, (
        "bowl_count only applies to Kitchen Sink - the product's REAL stored class is "
        "Water Closet, and a candidate's own proposed class must not gate past itself"
    )


def test_extract_scope_gate_uses_the_products_stored_class_not_a_models_proposed_one(
    api, db, monkeypatch
):
    """Same defect, end-to-end through the real route: the model reads the pasted
    text as naming BOTH a class and a bowl count, but the product's own stored class
    (Water Closet, from its real description) is what must decide whether bowl_count
    is in scope - not the model's candidate class."""
    client, allow = api
    allow.add("master_data.products.edit")
    # `class` is open-vocabulary (allowed_values: [] in the seed) - `_coerce` checks a
    # proposed value against what the CATALOG already holds (`open_vocabulary_values`),
    # so a second, unrelated Kitchen Sink product is seeded here to make "Kitchen
    # Sink" a value the model's proposal survives validation as, rather than being
    # dropped as an unknown value before ever reaching the scope gate this test pins.
    _product(db, "ZZT-EX-SCOPEGATE-KS", "SORENTO CERAMIC KITCHEN SINK ZZT-EX-SCOPEGATE-KS")
    db.commit()
    derive_for_code(db, "ZZT-EX-SCOPEGATE-KS", commit=True)

    _model_returning(
        {
            "specs": [
                {"key": "class", "value": "Kitchen Sink", "evidence": "kitchen sink style"},
                {"key": "bowl_count", "value": 2, "evidence": "2 bowl"},
            ]
        },
        monkeypatch,
    )
    product = _product(db, "ZZT-EX-SCOPEGATE-WC", "SORENTO ONE PIECE WC ZZT-EX-SCOPEGATE-WC")
    db.commit()
    derive_for_code(db, "ZZT-EX-SCOPEGATE-WC", commit=True)

    response = _extract(client, product.id, "Kitchen sink style, 2 bowl")

    assert response.status_code == 200, response.text
    by_key = _by_key(response.json())
    assert "bowl_count" not in by_key, (
        "the product's own stored class is Water Closet - bowl_count (Kitchen Sink "
        "only) must be gated on THAT, never on a proposed class override"
    )


# --------------------------------------------------------------------------- #
# BLOCKER (second review) - `propose_from_text` fires `code_suffix` rules against the
# PRODUCT'S OWN code, independently of whatever text was pasted (proven directly in
# tests/test_product_spec_propose_from_text.py::test_a_code_suffix_rule_still_fires,
# which pins that the lift keeps that pass and keeps stamping it `origin: "code"`).
# The route must not let a `code`-origin hit become a proposal here: pasted text is
# the only source this endpoint reads FROM - derivation already reads the code, via
# `derive_for_code`, and repeating that reading as if the pasted text said it is not
# what "extract from this text" means.
# --------------------------------------------------------------------------- #
def test_extract_never_proposes_a_code_origin_hit(api, db, monkeypatch):
    """Code ends `-GY` (`code_suffix` -> finish=grey, confirmed directly against
    `propose_from_text` above this product's own code). The description instead
    names "GOLDEN YELLOW" (a `FINISH_WORDS` token -> finish=golden_yellow), so the
    product's stored, derived finish differs from what the code suffix alone would
    say. The pasted text is completely inert - no finish word, no code, nothing a
    rule or a (stubbed absent) model could read - so the only way a finish proposal
    could appear is the code-origin hit leaking through from `product.product_code`.
    """
    client, allow = api
    allow.add("master_data.products.edit")
    _no_model(monkeypatch)
    product = _product(
        db, "ZZT-EX-CODEORIGIN-GY", "SORENTO BASIN GOLDEN YELLOW ZZT-EX-CODEORIGIN-GY"
    )
    db.commit()
    derive_for_code(db, "ZZT-EX-CODEORIGIN-GY", commit=True)
    stored = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-CODEORIGIN-GY")
        .first()
    )
    assert stored.values["finish"]["value"] == "golden_yellow", (
        "fixture assumption: the description-derived finish must differ from what "
        "the code suffix alone would say (grey), or this test cannot tell them apart"
    )

    response = _extract(
        client, product.id, "Two year warranty. Please contact your dealer."
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposals"] == [], (
        "the pasted text says nothing about finish - a code-origin hit must not "
        f"become a proposal, got: {body['proposals']!r}"
    )
    assert "finish" not in _by_key(body)


# --------------------------------------------------------------------------- #
# AI usage telemetry - a successful semantic extract writes ONE usage-log row, the
# same bookkeeping `understand_phrase` writes for `spec_search` (product_spec_
# understanding.py), discriminated by `feature="spec_extract"`. This is a SEPARATE
# table from `product_specifications`/`product_flyer_text` - AC-B.1's "writes
# nothing" is about product data, not about usage telemetry, so this does not
# relax the no-write guarantee the earlier test in this file pins.
# --------------------------------------------------------------------------- #
def test_extract_writes_one_ai_assistant_usage_log_row_on_a_semantic_extract(
    api, db, monkeypatch
):
    from app.models.ai_assistant import AIAssistantUsageLog
    from app.models.user import User

    client, allow = api
    allow.add("master_data.products.edit")
    db.add(User(id=_USER["id"], email=_USER["email"], name="Spec Extractor", status="ACTIVE"))
    db.commit()
    _model_returning(
        {"specs": [{"key": "trap_type", "value": "s_trap", "evidence": "S-Trap"}]}, monkeypatch
    )
    product = _product(db, "ZZT-EX-USAGELOG", "SORENTO ONE PIECE WC ZZT-EX-USAGELOG")
    db.commit()
    derive_for_code(db, "ZZT-EX-USAGELOG", commit=True)

    before_flyer_count = db.query(ProductFlyerText).count()
    before_spec = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-USAGELOG")
        .first()
    )
    before_snapshot = (dict(before_spec.values), dict(before_spec.provenance))
    assert db.query(AIAssistantUsageLog).count() == 0

    response = _extract(client, product.id, "A washdown WC with an S-trap outlet")

    assert response.status_code == 200, response.text
    db.expire_all()

    logs = db.query(AIAssistantUsageLog).all()
    assert len(logs) == 1, f"expected exactly one usage-log row, found {len(logs)}"
    assert logs[0].feature == "spec_extract"

    after_spec = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EX-USAGELOG")
        .first()
    )
    after_snapshot = (dict(after_spec.values), dict(after_spec.provenance))
    assert after_snapshot == before_snapshot, "the usage log write must not touch spec data"
    assert db.query(ProductFlyerText).count() == before_flyer_count


# --------------------------------------------------------------------------- #
# extractor model resolution: `extract_specs_from_text` must resolve the
# `spec_extractor` agent's own provider/model, not `spec_understanding`'s.
#
# `_resolve_provider` (product_spec_understanding.py) hardcodes
# `agent_model(db, AGENT_NAME)` where `AGENT_NAME = "spec_understanding"` - the SAME
# call `understand_phrase` makes - regardless of which function invoked it. The system
# PROMPT is already correctly asked for under `EXTRACTOR_AGENT_NAME = "spec_extractor"`
# (`get_prompt(db, EXTRACTOR_AGENT_NAME)` inside `extract_specs_from_text`), so the
# mismatch is easy to miss: the words the model reads are the extractor's, but the
# MODEL it reads them with is silently whatever an admin configured for the
# understanding agent instead.
# --------------------------------------------------------------------------- #
def test_extract_specs_from_text_resolves_the_spec_extractor_agents_own_model(db, monkeypatch):
    import app.services.product_spec_understanding as understanding

    calls: list[str] = []

    def _recording_agent_model(db_arg, name, label="production"):
        calls.append(name)
        return None, None

    monkeypatch.setattr(understanding, "agent_model", _recording_agent_model)
    # Belt as well as braces: force the "no configured key either" branch so this
    # cannot fall through to a real provider call regardless of local .env contents.
    monkeypatch.setattr(understanding.settings, "openai_api_key", "")

    understanding.extract_specs_from_text(db, "Brass Body", vocabulary=([], {}, {}))

    assert "spec_extractor" in calls, (
        f"extract_specs_from_text must resolve the spec_extractor agent's own model, "
        f"asked for: {calls!r}"
    )
