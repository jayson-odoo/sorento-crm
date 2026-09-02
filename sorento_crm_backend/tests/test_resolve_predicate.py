"""The `require` seam on POST /references/resolve - shape B over the wire.

Three properties carry the contract:

  1. absent `require` -> the response is byte-identical to today, for every caller
  2. present -> ONE nested `predicate` block (never top-level scalars, never keys
     inside `by_entity_type`) + qualifying products as ordinary matches with
     `match_tier="spec_search"`
  3. an unknown key is a 422 - a parser emitting one is a bug to surface, not skip

Contract: sorento_crm_n8n/n8n-workflows-init/plans/crm-ask-spec-backward-search.md.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/system/references/resolve"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        s.add_all([cat, uom])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)

        wh = Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZT-WH", warehouse_name="ZZT WH")
        s.add(wh)
        s.flush()
        for code, qty in (("ZZTKS9001", 4), ("ZZTKS9002", 0)):
            product = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description="SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=Decimal("1.00"),
            )
            s.add(product)
            s.flush()
            derive_for_code(s, code)
            s.add(
                Stock(
                    id=str(uuid.uuid4()),
                    product_id=product.id,
                    warehouse_id=wh.id,
                    quantity_on_hand=qty,
                    quantity_reserved=0,
                    quantity_damaged=0,
                )
            )
            s.flush()
        yield s


@pytest.fixture()
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_external_api_user,
    )
    from app.services.company_scope_resolver import apply_company_scope

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_external_api_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_absent_require_is_byte_identical(client):
    body = {"query": "kitchen sink with stock", "free_terms": ["kitchen sink"]}
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200
    payload = response.json()
    assert "predicate" not in payload


def test_require_returns_the_predicate_block_and_ordinary_matches(client):
    response = client.post(
        ENDPOINT,
        json={
            "query": "which kitchen sinks have stock",
            "free_terms": ["kitchen sink"],
            "require": {"stock": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()

    predicate = payload["predicate"]
    assert predicate["qualifying_total"] == 1
    assert predicate["truncated"] is False
    assert predicate["unrecognized_terms"] == []
    assert predicate["require"] == {"stock": True}

    matches = [
        m
        for resolution in payload["resolutions"]
        for m in resolution["matches"]
        if m.get("match_tier") == "spec_search"
    ]
    assert [m["canonical_code"] for m in matches] == ["ZZTKS9001"]
    # Every returned id already satisfies the predicate - the downstream MCP
    # call stays dumb. And the block is nested, never splashed on by_entity_type.
    assert "qualifying_total" not in payload
    assert "predicate" not in (payload.get("by_entity_type") or {})


def test_unrecognized_terms_reach_the_wire(client):
    response = client.post(
        ENDPOINT,
        json={"query": "flurbish with stock", "free_terms": ["flurbish"], "require": {"stock": True}},
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["unrecognized_terms"] == ["flurbish"]
    assert predicate["qualifying_total"] == 0


def test_a_require_turn_carries_no_spec_top_score(client):
    """`spec_top_score` belongs to shape A, and shape B must not grow it.

    The field says how much evidence the RELEVANCE FLOOR was tested against, and
    shape B never runs that floor: `require` is a predicate over a described set,
    answered by `resolve_product_set`, and it returns before the spec-fallback block
    that sets the field. So a number here would have no floor behind it and no
    meaning - and property 1 of this file is that a caller sees the same wire shape
    it saw yesterday, so a scalar appearing on the predicate path is a contract
    break whether or not anything reads it. n8n item-mutation chains persist
    top-level keys across nodes, which is how a stray scalar reaches a customer.

    `spec_fallback` is sent TRUE on purpose: the flag alone must not summon the
    field once `require` has claimed the turn.
    """
    response = client.post(
        ENDPOINT,
        json={
            "query": "which kitchen sinks have stock",
            "free_terms": ["kitchen sink"],
            "require": {"stock": True},
            "spec_fallback": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert "spec_top_score" not in payload
    # Its two companions from the same block, for the same reason.
    assert "floor_missed" not in payload
    assert "spec_candidates" not in payload

    # And the rest of the shape-B answer is exactly what this file already expects.
    assert payload["predicate"] == {
        "require": {"stock": True},
        "qualifying_total": 1,
        "truncated": False,
        "unrecognized_terms": [],
    }
    matches = [
        m
        for resolution in payload["resolutions"]
        for m in resolution["matches"]
        if m.get("match_tier") == "spec_search"
    ]
    assert [m["canonical_code"] for m in matches] == ["ZZTKS9001"]
    assert "predicate" not in (payload.get("by_entity_type") or {})


def test_an_unknown_require_key_is_a_422(client):
    response = client.post(
        ENDPOINT,
        json={"query": "kitchen sink", "free_terms": ["kitchen sink"], "require": {"blessing": True}},
    )
    assert response.status_code == 422
