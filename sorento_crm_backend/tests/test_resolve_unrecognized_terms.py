"""S3: name every qualifier that could not be honoured, in the right channel.

Two honesty channels, and a customer reads them as two different sentences:

  * `spec_unmet` - a KNOWN key nothing on offer can satisfy. "Thickness isn't
    recorded for these." The word was understood; the catalogue is silent.
  * `unrecognized_terms` - a word that named nothing at all. "I don't know what
    'flurbish' means." Nothing was understood, so the only honest reply is to
    ask.

Shape B (the `require` branch) already speaks both. Shape A said only the first,
so a qualifier binding to no key at all read as success.

Precision is the whole design here: telling a customer we do not know what
"kitchen" means is far worse than staying quiet about one alien word, so a word
is reported ONLY when nothing in the registry, the class vocabulary or the brand
table knows it.

The third behaviour pinned here is the footer-strip exemption. Spec rows answer
DESCRIPTIONS; they never vouch for a CODE the catalogue does not contain, so a
made-up code stays in `unresolved_tokens` even when the sentence around it found
sinks.

Plan: documentation/plans/PLAN-spec-raw-text-search.md (S3).
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
from app.services.product_spec_search import unrecognized_words
from tests._pg_fixture import blank_session

RESOLVE = "/api/v1/system/references/resolve"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}
_REFS: dict = {}


def _product(db, code, description, *, brand_id=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
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
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        s.add_all([cat, uom, sorento])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "sorento": sorento.id})

        # The dimension quad's 4th number is the thickness, so both sinks carry a
        # thickness value: "thickness" is a key the catalogue can answer.
        _product(
            s,
            "ZZTKS2B",
            "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
            brand_id=sorento.id,
        )
        _product(
            s,
            "ZZTKS1B",
            "SORENTO S/STEEL SINGLE BOWL KITCHEN SINK (860X500X200X1.0MM)",
            brand_id=sorento.id,
        )
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


def _resolve_raw(client, sentence: str) -> dict:
    return client.post(RESOLVE, json={"query": sentence, "spec_fallback": True}).json()


# --------------------------------------------------------------------------- #
# the endpoint: an alien word is named, and named only once                     #
# --------------------------------------------------------------------------- #
def test_an_alien_word_is_named(client):
    body = _resolve_raw(client, "double bowl kitchen sink with flurbish")
    assert body.get("unrecognized_terms") == ["flurbish"]


def test_the_sinks_are_still_offered_alongside_the_admission(client):
    body = _resolve_raw(client, "double bowl kitchen sink with flurbish")
    assert body.get("spec_candidates"), "one unknown word must not empty the shortlist"


def test_an_alien_word_is_never_reported_as_an_unmet_spec(client):
    body = _resolve_raw(client, "double bowl kitchen sink with flurbish")
    unmet = " ".join(str(entry) for entry in body.get("spec_unmet") or [])
    assert "flurbish" not in unmet.lower()


def test_a_known_key_is_not_an_unknown_word(client):
    # "thickness" is a registry key and the number binds to it, so nothing here
    # is alien - whatever the catalogue can or cannot answer about the value.
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 9.9mm")
    assert body.get("unrecognized_terms") == []


def test_a_clean_sentence_admits_nothing(client):
    body = _resolve_raw(client, "stainless steel kitchen sink")
    assert body.get("unrecognized_terms") == []


def test_a_brand_word_is_known(client):
    body = _resolve_raw(client, "sorento kitchen sink")
    assert body.get("unrecognized_terms") == []


def test_an_explicit_caller_term_is_reported_verbatim(client):
    body = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink",
            "spec_fallback": True,
            "free_terms": ["double bowl kitchen sink", "flurbish grommet"],
        },
    ).json()
    assert "flurbish grommet" in (body.get("unrecognized_terms") or [])


# --------------------------------------------------------------------------- #
# the footer strip: spec rows answer descriptions, never codes                  #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def coded_turn(client) -> dict:
    return client.post(
        RESOLVE,
        json={
            "query": "ZZTKS999 kitchen sink",
            "tokens": ["ZZTKS999", "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()


def test_the_description_is_still_answered(coded_turn):
    assert coded_turn.get("spec_candidates")
    assert "kitchen sink" not in (coded_turn.get("unresolved_tokens") or [])


def test_a_code_the_catalogue_lacks_is_still_reported(coded_turn):
    assert "ZZTKS999" in (coded_turn.get("unresolved_tokens") or [])


# --------------------------------------------------------------------------- #
# the vocabulary itself                                                         #
# --------------------------------------------------------------------------- #
def test_stopwords_are_never_reported(db):
    assert unrecognized_words(db, "i want to find me a kitchen sink please") == []


def test_measurements_are_never_reported(db):
    assert unrecognized_words(db, "kitchen sink 820mm wide and 1.2mm thick") == []


def test_registry_words_are_known(db):
    assert unrecognized_words(db, "double bowl stainless steel undermount sink") == []


def test_class_words_are_known(db):
    assert unrecognized_words(db, "kitchen sink") == []


def test_brand_words_are_known(db):
    assert unrecognized_words(db, "sorento sink") == []


def test_an_alien_word_is_caught(db):
    assert unrecognized_words(db, "kitchen sink with flurbish") == ["flurbish"]


def test_aliens_are_reported_in_sentence_order_once_each(db):
    assert unrecognized_words(db, "flurbish kitchen sink quixotic flurbish") == [
        "flurbish",
        "quixotic",
    ]
