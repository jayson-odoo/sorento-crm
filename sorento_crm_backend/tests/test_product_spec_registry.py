"""The Spec Registry: one vocabulary, read by both the ranker and the chatbot parser.

Spec search only works if the CRM and the n8n parser agree on what a spec key is and
which values it may take. Holding that list in two places guarantees they drift, and
the drift is silent: the parser emits `wall_mounted`, the ranker looks for `wall_hung`,
and every query quietly scores worse with nothing in the logs.

So the registry is the single source of truth. The parser reads it over HTTP to build
its extraction prompt, and the ranker reads the same rows to weight a match.

Ticket: jayson-odoo/sorento-crm#73. Contract:
documentation/plans/products/spec-search-acceptance-criteria.md AC-T0b-01 .. AC-T0b-05.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.product_spec import ProductSpecRegistry
from app.services.product_spec_registry import (
    PILOT_SPEC_KEYS,
    seed_spec_registry,
)
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/master-data/spec-registry"
_USER = {"id": str(uuid.uuid4()), "email": "specsearch@example.com"}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture()
def client(db, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    # The route is gated on master_data.products.view. The blank schema has no role
    # grants, so grant it here rather than seeding an entire RBAC chain: this file is
    # testing the registry, and a separate test covers the permission itself.
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def denied_client(db, monkeypatch):
    """A caller holding no permissions, to prove the route is actually gated."""
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: False
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _keys(db) -> dict[str, ProductSpecRegistry]:
    return {r.spec_key: r for r in db.query(ProductSpecRegistry).all()}


# AC-T0b-02: the pilot seed registers exactly the keys the tracer needs, no more.
def test_seed_registers_exactly_the_pilot_keys(db):
    seed_spec_registry(db)
    assert set(_keys(db)) == set(PILOT_SPEC_KEYS)


def test_every_seeded_key_is_active_and_typed(db):
    seed_spec_registry(db)
    for key, row in _keys(db).items():
        assert row.is_active is True, key
        assert row.data_type in {"enum", "numeric", "boolean"}, key
        assert row.label, key


def test_measured_numeric_keys_carry_a_unit(db):
    """Anything measured is in millimetres. A count is not measured, so it has no unit.

    Rendering "2 mm" for a double bowl sink would be worse than wrong: it would embed a
    dimension phrase into a sentence the ranker compares against real dimensions.
    """
    counts = {"bowl_count"}
    seed_spec_registry(db)
    for key, row in _keys(db).items():
        if row.data_type != "numeric":
            continue
        if key in counts:
            assert row.unit is None, key
        else:
            assert row.unit == "mm", key


def test_enum_keys_carry_allowed_values(db):
    seed_spec_registry(db)
    rows = _keys(db)
    # `class` and `brand` are open vocabularies sourced from product_categories, so
    # they are the deliberate exception: a closed list would go stale the moment a
    # category is added.
    for key in ("material", "mounting", "finish", "control_type", "shape"):
        assert rows[key].allowed_values, key


# AC-T0b-03: diameter only exists for shapes that HAVE one. Ungated, it would be
# proposed for a rectangular sink, where it is meaningless.
def test_diameter_is_gated_on_shape(db):
    seed_spec_registry(db)
    gate = _keys(db)["diameter"].applies_when
    assert gate == {"shape": ["round", "square"]}


def test_rectangular_dimensions_are_not_shape_gated(db):
    # Shape is frequently unknown (no ROUND or SQUARE token in the description), and
    # gating length/width on it would drop every unlabelled rectangular product.
    seed_spec_registry(db)
    rows = _keys(db)
    for key in ("dim_length", "dim_width", "dim_height"):
        assert rows[key].applies_when == {}, key


def test_measured_coverage_is_recorded(db):
    # Recorded at seed time so a later reviewer can see WHY a key is weighted low,
    # rather than rediscovering the measurement.
    seed_spec_registry(db)
    assert _keys(db)["material"].measured_coverage > 0


# AC-T0b-05: re-seeding is safe. It runs on every deploy as the map grows.
def test_seed_is_idempotent(db):
    first = seed_spec_registry(db)
    second = seed_spec_registry(db)
    assert first["created"] == len(PILOT_SPEC_KEYS)
    assert second["created"] == 0
    assert second["updated"] == 0


# AC-T0b-05: weights are tuned against the eval baseline by hand. A re-seed that
# reverted that tuning would silently undo the only calibration the ranker has.
def test_reseed_preserves_a_hand_tuned_rank_weight(db):
    seed_spec_registry(db)
    row = _keys(db)["material"]
    row.rank_weight = 9.5
    db.flush()

    seed_spec_registry(db)

    assert float(_keys(db)["material"].rank_weight) == 9.5


def test_reseed_preserves_a_hand_deactivated_key(db):
    seed_spec_registry(db)
    row = _keys(db)["thickness"]
    row.is_active = False
    db.flush()

    seed_spec_registry(db)

    assert _keys(db)["thickness"].is_active is False


def test_reseed_repairs_a_corrupted_allowed_values(db):
    # Vocabulary is owned by the seed, unlike weights and activation which are owned
    # by whoever tuned them. A wrong allowed_values breaks parser and ranker agreement,
    # so it must be repaired rather than preserved.
    seed_spec_registry(db)
    row = _keys(db)["mounting"]
    row.allowed_values = ["nonsense"]
    db.flush()

    result = seed_spec_registry(db)

    assert "wall_hung" in _keys(db)["mounting"].allowed_values
    assert result["updated"] == 1


# AC-T0b-04: the endpoint the n8n parser reads to build its extraction prompt.
def test_endpoint_returns_the_active_registry(client, db):
    seed_spec_registry(db)

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    body = response.json()
    assert {k["spec_key"] for k in body["keys"]} == set(PILOT_SPEC_KEYS)


def test_endpoint_omits_inactive_keys(client, db):
    # bowl_count ships inactive in T1 precisely so it never reaches the parser prompt.
    # If an inactive key leaked, the parser would extract a spec nothing can match.
    seed_spec_registry(db)
    db.query(ProductSpecRegistry).filter(
        ProductSpecRegistry.spec_key == "thickness"
    ).one().is_active = False
    db.flush()

    keys = {k["spec_key"] for k in client.get(ENDPOINT).json()["keys"]}

    assert "thickness" not in keys
    assert "material" in keys


def test_endpoint_carries_the_vocabulary_the_parser_needs(client, db):
    seed_spec_registry(db)

    material = next(
        k for k in client.get(ENDPOINT).json()["keys"] if k["spec_key"] == "material"
    )

    assert material["data_type"] == "enum"
    assert "stainless_steel" in material["allowed_values"]
    assert "s/steel" in [s.lower() for s in material["synonyms"]["stainless_steel"]]


def test_endpoint_exposes_the_diameter_gate(client, db):
    seed_spec_registry(db)

    diameter = next(
        k for k in client.get(ENDPOINT).json()["keys"] if k["spec_key"] == "diameter"
    )

    assert diameter["applies_when"] == {"shape": ["round", "square"]}


def test_endpoint_is_cacheable(client, db):
    # The parser reads this on every turn and it changes about never, so it carries a
    # validator. Without one, a hot path re-renders the whole vocabulary per message.
    seed_spec_registry(db)

    response = client.get(ENDPOINT)

    assert response.headers.get("etag")
    assert response.json()["updated_at"] is not None


def test_endpoint_returns_304_for_a_matching_etag(client, db):
    seed_spec_registry(db)
    etag = client.get(ENDPOINT).headers["etag"]

    again = client.get(ENDPOINT, headers={"If-None-Match": etag})

    assert again.status_code == 304


def test_endpoint_is_permission_gated(denied_client, db):
    seed_spec_registry(db)
    assert denied_client.get(ENDPOINT).status_code == 403


def test_synonyms_map_customer_language_onto_values(db):
    seed_spec_registry(db)
    synonyms = _keys(db)["material"].synonyms
    assert "s/steel" in [s.lower() for s in synonyms["stainless_steel"]]

    mounting = _keys(db)["mounting"].synonyms
    assert "wall mounted" in [s.lower() for s in mounting["wall_hung"]]
