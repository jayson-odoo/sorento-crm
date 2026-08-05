"""The `spec_fallback` seam on POST /references/resolve.

Spec search hangs off the resolver's MISS path. Three properties matter more than the
feature itself, because they are what make it safe to ship into a live chatbot:

  1. absent or false  -> the response is byte-identical to today, for every caller
  2. true, but the normal probes resolved something -> spec search does NOT run
  3. true, and nothing resolved -> candidates arrive in a SEPARATE field

Ticket: jayson-odoo/sorento-crm#76. Contract: AC-T0e-01 .. AC-T0e-04.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/system/references/resolve"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}
_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        s.add_all([cat, uom])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update({"cat": cat.id, "uom": uom.id})

        product = Product(
            id=str(uuid.uuid4()),
            product_code="ZZTKS9001",
            product_name="ZZTKS9001",
            description="SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        s.add(product)
        s.flush()
        derive_for_code(s, "ZZTKS9001")
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
    # The route resolves get_current_user_or_api_key underneath get_external_api_user,
    # so overriding only the outer one leaves the request 401ing. A 401 body has no
    # spec_candidates either, which makes the "inert by default" tests pass for the
    # wrong reason - a green that cannot fail.
    app.dependency_overrides[get_external_api_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_the_fixture_is_actually_authenticated(client):
    """Guard the guards: every 'no spec_candidates' assertion below would also pass
    against a 401 body, so prove the request is really reaching the resolver."""
    response = client.post(ENDPOINT, json={"query": "ZZTKS9001"})
    assert response.status_code == 200
    assert "resolutions" in response.json()


# AC-T0e-01: inert by default. This is the property that lets it ship dark.
def test_without_the_flag_the_response_is_unchanged(client):
    body = client.post(ENDPOINT, json={"query": "something that resolves to nothing"}).json()

    assert "spec_candidates" not in body
    assert "floor_missed" not in body


def test_with_the_flag_false_the_response_is_unchanged(client):
    body = client.post(
        ENDPOINT, json={"query": "nothing here", "spec_fallback": False}
    ).json()

    assert "spec_candidates" not in body


# AC-T0e-02: the fallback fires on a miss and lands in its OWN field, so a caller
# reading `resolutions` cannot accidentally treat a guess as a resolution.
def test_a_description_miss_returns_spec_candidates(client):
    body = client.post(
        ENDPOINT,
        json={
            "query": "stainless steel kitchen sink",
            "spec_fallback": True,
            "extracted_specs": [
                {"key": "class", "value": "Kitchen Sink"},
                {"key": "material", "value": "stainless_steel"},
            ],
            "free_terms": ["kitchen sink"],
        },
    ).json()

    assert body["floor_missed"] is False
    assert "ZZTKS9001" in [c["product_code"] for c in body["spec_candidates"]]
    assert "resolutions" in body, "the normal resolver payload must survive untouched"


# AC-T0e-03: a fallback, never a parallel path.
def test_spec_search_does_not_run_when_the_code_resolves(client):
    body = client.post(
        ENDPOINT,
        json={
            "query": "ZZTKS9001",
            "spec_fallback": True,
            "extracted_specs": [{"key": "class", "value": "Kitchen Sink"}],
        },
    ).json()

    resolved = any(r.get("matches") for r in body.get("resolutions", []))
    assert resolved, "the code should resolve normally"
    assert "spec_candidates" not in body


def test_a_floor_miss_returns_no_candidates(client):
    body = client.post(
        ENDPOINT,
        json={
            "query": "flux capacitor",
            "spec_fallback": True,
            "extracted_specs": [],
            "free_terms": ["flux capacitor"],
        },
    ).json()

    assert body["floor_missed"] is True
    assert body["spec_candidates"] == []
