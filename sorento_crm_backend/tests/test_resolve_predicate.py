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


def test_an_unknown_require_key_is_a_422(client):
    response = client.post(
        ENDPOINT,
        json={"query": "kitchen sink", "free_terms": ["kitchen sink"], "require": {"blessing": True}},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Attribute-first asks S1 (PLAN-attribute-first-asks.md) - AC-1304 to AC-1309   #
# --------------------------------------------------------------------------- #


def _three_bidets(db):
    """ACC-BIDET / CAB-BIDET / SRT-BIDET - the exact three codes AC-1319's own worked
    example names. ACC-BIDET and SRT-BIDET carry a certificate, CAB-BIDET does not - TWO
    certified products on purpose (not one): a test that asserts "only SRT-BIDET
    qualifies" must fail today for the CORRECT reason (no brand scope applied yet), not
    pass by coincidence because an unrestricted require-only scan over an otherwise-empty
    scratch schema happens to have only one certified row.
    """
    from app.models.certificate import Certificate, CertificateProduct

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    codes = ["ACC-BIDET", "CAB-BIDET", "SRT-BIDET"]
    certified_codes = {"ACC-BIDET", "SRT-BIDET"}
    for code in codes:
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description="BIDET SPRAY SET",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        if code in certified_codes:
            cert = Certificate(
                id=str(uuid.uuid4()),
                scheme="ZZT-SIRIM",
                certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}",
                status="active",
            )
            db.add(cert)
            db.flush()
            db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
            db.flush()
    return codes


def test_require_is_ignored_when_a_product_token_resolved_exactly(client, db):
    """AC-1305: a caller token that resolved to an EXACT (or head_code) product match
    already answered a full code - the `require` predicate must not run over it at all,
    so the response is byte-identical to the same request without `require`."""
    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    db.add(
        Product(
            id=str(uuid.uuid4()),
            product_code="ZZTEXACT1",
            product_name="ZZTEXACT1",
            description="SORENTO EXACT CODE PRODUCT",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
    )
    db.flush()

    with_require = client.post(
        ENDPOINT,
        json={"query": "ZZTEXACT1", "tokens": ["ZZTEXACT1"], "require": {"stock": True}},
    )
    without_require = client.post(
        ENDPOINT,
        json={"query": "ZZTEXACT1", "tokens": ["ZZTEXACT1"]},
    )
    assert with_require.status_code == 200
    assert without_require.status_code == 200
    with_body = with_require.json()
    without_body = without_require.json()
    # `elapsed_ms` is a real wall-clock measurement (`entity_resolver.py`'s own timing),
    # never expected to be equal across two separate calls - drop it before comparing.
    with_body.pop("elapsed_ms", None)
    without_body.pop("elapsed_ms", None)
    assert with_body == without_body
    assert "predicate" not in with_body


def test_require_runs_when_only_partial_product_matches_exist(client, db):
    """AC-1305: no product token resolved exactly (three distinct BIDET codes, no
    exact code typed) - HAS must run."""
    _three_bidets(db)
    response = client.post(
        ENDPOINT,
        json={"query": "bidet", "tokens": ["bidet"], "require": {"certificate": True}},
    )
    assert response.status_code == 200
    assert "predicate" in response.json()


def test_described_set_unions_lookup_matches_bindings_and_brand(client, db):
    """AC-1306: the described set is the union of the LOOKUP-matched product ids
    ("bidet" name-matches all three) and any class/product_type/brand binding derived
    from the query - and a brand scopes the whole set. Only SRT-BIDET is both Sorento
    and certified."""
    from app.models.product import Brand

    sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
    cabana = Brand(id=str(uuid.uuid4()), brand_code="ZZT-CAB", brand_name="CABANA")
    db.add_all([sorento, cabana])
    db.flush()

    _three_bidets(db)
    by_code = {p.product_code: p for p in db.query(Product).filter(Product.product_code.in_(
        ["ACC-BIDET", "CAB-BIDET", "SRT-BIDET"]
    ))}
    by_code["ACC-BIDET"].brand_id = cabana.id
    by_code["CAB-BIDET"].brand_id = cabana.id
    by_code["SRT-BIDET"].brand_id = sorento.id
    db.flush()

    response = client.post(
        ENDPOINT,
        json={
            "query": "which sorento bidet has cert",
            "tokens": ["sorento", "bidet"],
            "require": {"certificate": True},
            "predicate_words": ["cert"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    predicate = payload["predicate"]
    assert predicate["qualifying_total"] == 1
    matches = [
        m
        for resolution in payload["resolutions"]
        for m in resolution["matches"]
        if m.get("match_tier") == "spec_search"
    ]
    assert [m["canonical_code"] for m in matches] == ["SRT-BIDET"]


def test_predicate_matches_carry_the_shape_the_fetch_reads(client, db):
    """AC-1309: qualifying ids land in `resolutions[].matches` shaped exactly like every
    other product match (`entity_type`, `match_tier="spec_search"`, `uuid`,
    `canonical_code`), and `result["predicate"]` carries exactly the four documented
    keys - nothing more, nothing less."""
    _three_bidets(db)
    response = client.post(
        ENDPOINT,
        json={"query": "bidet", "tokens": ["bidet"], "require": {"certificate": True}},
    )
    assert response.status_code == 200
    payload = response.json()

    matches = [
        m
        for resolution in payload["resolutions"]
        for m in resolution["matches"]
        if m.get("match_tier") == "spec_search"
    ]
    assert matches, "expected at least one spec_search match (SRT-BIDET is certified)"
    for m in matches:
        assert m["entity_type"] == "product"
        assert m["match_tier"] == "spec_search"
        assert m.get("uuid")
        assert m.get("canonical_code")

    assert set(payload["predicate"].keys()) == {
        "require",
        "qualifying_total",
        "truncated",
        "unrecognized_terms",
    }


def test_predicate_words_is_accepted_on_the_request(client):
    """AC-1304 (half): `predicate_words` is a documented field on the request body, not
    a value pydantic silently drops on the way in - a request with it and one without it
    (and no `require`) must answer identically either way."""
    body = {"query": "kitchen sink", "free_terms": ["kitchen sink"]}
    without = client.post(ENDPOINT, json=body)
    with_words = client.post(ENDPOINT, json={**body, "predicate_words": ["cert"]})
    assert without.status_code == 200
    assert with_words.status_code == 200
    without_body = without.json()
    with_words_body = with_words.json()
    without_body.pop("elapsed_ms", None)
    with_words_body.pop("elapsed_ms", None)
    assert without_body == with_words_body
