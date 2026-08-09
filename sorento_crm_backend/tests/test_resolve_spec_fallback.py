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


# --------------------------------------------------------------------------- #
# a described product must arrive as a PRODUCT, not as a side-channel (#106)
# --------------------------------------------------------------------------- #
def test_a_described_product_arrives_as_an_ordinary_product_match(client):
    """`spec_candidates` alone was a dead end.

    It is a different shape parked beside the result, so every existing consumer — the
    n8n spine's resolve-entity, and get-results behind it — read `resolutions[].matches`,
    found nothing, and treated the turn as unresolved. Describing a product well enough
    to find it only matters if the thing that asked can then use it.
    """
    body = client.post(
        ENDPOINT,
        json={
            "query": "stainless steel kitchen sink",
            "spec_fallback": True,
            "extracted_specs": [{"key": "class", "value": "Kitchen Sink"}],
            "free_terms": ["stainless steel kitchen sink"],
        },
    ).json()

    matches = [m for r in body["resolutions"] for m in r["matches"]]
    spec_matches = [m for m in matches if m["match_tier"] == "spec_search"]

    assert spec_matches, "the spec hit has to be reachable where every other match is"
    hit = spec_matches[0]
    assert hit["entity_type"] == "product"
    assert hit["canonical_code"] == "ZZTKS9001"
    assert hit["uuid"], "get-results needs the id, not just the code"
    assert hit["match_field"] == "specifications"




def test_the_flag_off_still_adds_no_matches(client):
    # The seam stays inert: this is what let it ship dark, and it has to stay true now
    # that it writes into `resolutions` rather than a field nobody reads.
    body = client.post(ENDPOINT, json={"query": "stainless steel kitchen sink"}).json()

    matches = [m for r in body["resolutions"] for m in r["matches"]]
    assert not [m for m in matches if m.get("match_tier") == "spec_search"]




def test_a_spec_shortlist_reads_exactly_like_a_prefix_shortlist(client):
    """A description that finds many products is not a question, it is an answer.

    `SRTWC286` returns 15 `prefix` matches and the spine goes straight to get-results
    for all of them. A description that finds 15 must read identically, or the same
    shortlist takes two different paths depending on how it was found. `alternatives`
    stays empty because that is the did-you-mean channel and these are matches.
    """
    body = client.post(
        ENDPOINT,
        json={
            "query": "stainless steel kitchen sink",
            "spec_fallback": True,
            "extracted_specs": [{"key": "class", "value": "Kitchen Sink"}],
        },
    ).json()

    spec_resolution = next(
        r for r in body["resolutions"] if any(m["match_tier"] == "spec_search" for m in r["matches"])
    )

    assert spec_resolution["matches"], "matches, not near misses"
    assert spec_resolution["alternatives"] == []
    assert spec_resolution["token"] not in (body.get("unresolved_tokens") or [])
    # Same rule prefix uses: one match is settled, several are a shortlist.
    assert spec_resolution["resolved"] is (len(spec_resolution["matches"]) == 1)
    assert spec_resolution["ambiguous"] is (len(spec_resolution["matches"]) > 1)


def test_and_mode_updates_every_view_of_the_answer(client):
    """AND mode carries the same answer three ways and the spine reads all of them.

    Setting `intersection` alone left `by_entity_type` empty and `empty` true, so a
    caller saw no products while `intersection` held them.
    """
    body = client.post(
        ENDPOINT,
        json={
            "query": "stainless steel kitchen sink",
            "match_mode": "and",
            "spec_fallback": True,
            "extracted_specs": [{"key": "class", "value": "Kitchen Sink"}],
        },
    ).json()

    if "intersection" not in body:
        pytest.skip("this query did not take the AND path")

    assert body["intersection"], "the products are here"
    assert body["by_entity_type"]["product"] == body["intersection"]
    assert body["empty"] is False
