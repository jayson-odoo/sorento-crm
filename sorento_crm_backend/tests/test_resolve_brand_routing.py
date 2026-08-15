"""S2: a brand is answered as a brand, and a miss the ranker answered is cleared.

Live turn 12303509: tokens ["Sorento", "double bowl kitchen sink"] in OR shape.
"Sorento" prefix-matched stale codes (SORENTOBAG, SORENTO188 "NOT USE THIS CODE"),
so the zero-match gate never fired, the descriptive token never reached the spec
ranker, and the customer was shown 4 junk products plus "Couldn't find: double
bowl kitchen sink".

Three behaviours are pinned here:
  - the gate fires when ANY OR-shape token found nothing (a token that matched
    nothing is unanswered by definition),
  - a brand word binds as a `brand` spec from the `brands` table, not from
    registry synonyms (the registry `brand` row ships empty, and a new brand must
    work the day it is added),
  - once the ranker HAS answered, a code that merely CONTAINS the brand word is
    catalogue noise and stops headlining, while an exact full code still resolves.

Counterweights: junk beats silence (nothing is suppressed when the ranker found
nothing), and an exact code is still a code.

Plan: documentation/plans/PLAN-spec-raw-text-search.md (S2).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session

RESOLVE = "/api/v1/system/references/resolve"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}
_REFS: dict = {}


def _product(db, code, description, *, category, brand_id=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=category,
        brand_id=brand_id,
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


@pytest.fixture
def db():
    with blank_session() as s:
        # SRT-KS decodes to the Kitchen Sink class; SRT-ACC is the catalog's own
        # accessory bucket, which `product_class_signal` marks non-searchable -
        # which is exactly where the stale brand-prefixed codes live.
        sink_cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"
        )
        junk_cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-ACC", category_name="SRT-ACC"
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        cabana = Brand(id=str(uuid.uuid4()), brand_code="ZZT-CB", brand_name="CABANA")
        s.add_all([sink_cat, junk_cat, uom, sorento, cabana])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update(
            {
                "cat": sink_cat.id,
                "junk_cat": junk_cat.id,
                "uom": uom.id,
                "sorento": sorento.id,
                "cabana": cabana.id,
            }
        )

        # The products the customer actually meant. Descriptions copied from the
        # live catalogue's shape: the dimension quad's 4th number is thickness.
        _product(
            s,
            "ZZTKS2B",
            "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
            category=sink_cat.id,
            brand_id=sorento.id,
        )
        _product(
            s,
            "ZZTKS1B",
            "SORENTO S/STEEL SINGLE BOWL KITCHEN SINK (860X500X200X1.0MM)",
            category=sink_cat.id,
            brand_id=sorento.id,
        )
        # What the code probes matched in the live turn: the brand word is in the
        # CODE, and the row carries no brand and no class of its own.
        _product(s, "SORENTOBAG", "SORENTO PAPER BAG", category=junk_cat.id)
        _product(s, "SORENTO188", "NOT USE THIS CODE", category=junk_cat.id)
        _product(s, "CABANABAG", "CABANA PAPER BAG", category=junk_cat.id)
        yield s


@pytest.fixture()
def client(db):
    from app.database import get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_external_api_user,
    )
    from app.main import app
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


def _codes_in_resolutions(body: dict) -> list[str]:
    return [
        str(m.get("canonical_code") or "")
        for tr in body.get("resolutions") or []
        for m in tr.get("matches") or []
    ]


def _resolution(body: dict, token: str) -> dict | None:
    for tr in body.get("resolutions") or []:
        if (tr.get("token") or "").strip().lower() == token.strip().lower():
            return tr
    return None


# --------------------------------------------------------------------------- #
# the live turn, replayed                                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def turn_12303509(client) -> dict:
    return client.post(
        RESOLVE,
        json={
            "query": "sorento double bowl kitchen sink",
            "tokens": ["Sorento", "double bowl kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()


def test_the_described_sink_reaches_the_ranker(turn_12303509):
    assert turn_12303509.get("spec_candidates"), (
        "a token that matched nothing is unanswered, so the spec gate must fire"
    )


def test_the_double_bowl_sink_is_the_answer(turn_12303509):
    codes = [c["product_code"] for c in turn_12303509["spec_candidates"]]
    assert codes[0] == "ZZTKS2B"


def test_the_brand_word_is_scored_as_a_brand(turn_12303509):
    assert "brand" in turn_12303509["spec_candidates"][0]["matched_specs"]


def test_no_stale_brand_prefixed_code_headlines(turn_12303509):
    codes = _codes_in_resolutions(turn_12303509)
    assert "SORENTOBAG" not in codes
    assert "SORENTO188" not in codes


def test_the_description_is_no_longer_reported_as_a_miss(turn_12303509):
    assert "double bowl kitchen sink" not in (turn_12303509.get("unresolved_tokens") or [])


# --------------------------------------------------------------------------- #
# brand binding: sourced from the brands table, never hand-seeded synonyms      #
# --------------------------------------------------------------------------- #
def test_a_brand_word_binds_from_the_brands_table(db):
    from app.services.product_spec_search import resolve_terms_to_specs

    entries = resolve_terms_to_specs(db, ["sorento double bowl kitchen sink"])
    assert {"key": "brand", "value": "SORENTO"} in entries


def test_a_sentence_naming_no_brand_binds_none(db):
    from app.services.product_spec_search import resolve_terms_to_specs

    entries = resolve_terms_to_specs(db, ["double bowl kitchen sink"])
    assert not [e for e in entries if e["key"] == "brand"]


# --------------------------------------------------------------------------- #
# counterweights                                                                #
# --------------------------------------------------------------------------- #
def test_an_exact_full_code_still_resolves_as_a_code(client):
    body = client.post(
        RESOLVE,
        json={
            "query": "SORENTOBAG",
            "tokens": ["SORENTOBAG"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert "SORENTOBAG" in _codes_in_resolutions(body)


def test_junk_stays_when_the_ranker_answered_nothing(client):
    # Nothing in the catalog carries the CABANA brand, and "flux capacitor" names
    # no class, so the ranker has nothing to offer. Junk beats silence: the brand
    # token keeps the rows the code probes found.
    body = client.post(
        RESOLVE,
        json={
            "query": "cabana flux capacitor",
            "tokens": ["Cabana", "flux capacitor"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert not body.get("spec_candidates")
    assert "CABANABAG" in _codes_in_resolutions(body)


# --------------------------------------------------------------------------- #
# the gate: any unanswered token opens the spec path                            #
# --------------------------------------------------------------------------- #
def test_one_resolved_token_no_longer_hides_an_unanswered_one(client):
    body = client.post(
        RESOLVE,
        json={
            "query": "ZZTKS2B double bowl kitchen sink",
            "tokens": ["ZZTKS2B", "double bowl kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates"), "a zero-match resolution must open the spec path"
    assert _resolution(body, "ZZTKS2B") is not None
