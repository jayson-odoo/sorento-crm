"""S1: the resolve endpoint reads RAW customer text - no parser-side extraction.

The Product Specifications page already handles a raw sentence because its
preview endpoint runs `understand_phrase` (word-level, no LLM) before ranking.
The resolve endpoint gated the same call behind the LLM opt-in flag, so a raw
sentence arrived with no specs and no free_terms and the ranker was blind -
which is how n8n's parser-built free_terms became a lossy hop that dropped
"thickness 1.0mm" in live turn 12303548.

These tests drive POST /resolve with ONLY {query, spec_fallback} - paraphrases,
never keyword echoes (standing rule) - and pin parity with the preview endpoint
so the two readings can never drift apart again.

Plan: documentation/plans/PLAN-spec-raw-text-search.md (S1).
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

RESOLVE = "/api/v1/system/references/resolve"
PREVIEW = "/api/v1/master-data/product-specifications/preview-search"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}
_REFS: dict = {}


def _product(db, code, description):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
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
        s.add_all([cat, uom])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update({"cat": cat.id, "uom": uom.id})

        # The preview endpoint enforces master_data.products.view against the
        # acting user; a superadmin role short-circuits the check true.
        from app.models.user import User, UserRole, UserRoleAssignment

        role = UserRole(
            id=str(uuid.uuid4()),
            slug="superadmin",
            name="ZZT Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
        user = User(id=_USER["id"], email=_USER["email"], name="ZZT N8N", status="ACTIVE")
        s.add_all([role, user])
        s.flush()
        s.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        s.flush()
        # Descriptions copied from the live catalogue's shapes: the dimension quad's
        # 4th number is the thickness, "DOUBLE BOWL" is stated in words.
        _product(s, "ZZTKS12", "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)")
        _product(s, "ZZTKS10", "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.0MM)")
        _product(s, "ZZTKS1B", "SORENTO S/STEEL SINGLE BOWL KITCHEN SINK (860X500X200X1.0MM)")
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


def _resolve_raw(client, sentence: str) -> dict:
    return client.post(RESOLVE, json={"query": sentence, "spec_fallback": True}).json()


def _spec_codes(body: dict) -> list[str]:
    return [c["product_code"] for c in body.get("spec_candidates", [])]


# --------------------------------------------------------------------------- #
# raw sentence in, ranked products out - nothing else supplied                  #
# --------------------------------------------------------------------------- #
def test_a_raw_sentence_alone_reaches_the_ranker(client):
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.2mm")
    assert body.get("spec_candidates"), "raw text must feed the ranker without free_terms"
    assert body["floor_missed"] is False


def test_the_stated_thickness_ranks_its_sink_first(client):
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.2mm")
    codes = _spec_codes(body)
    assert codes and codes[0] == "ZZTKS12"
    top = body["spec_candidates"][0]
    assert "thickness" in top["matched_specs"]


def test_value_first_word_order_reads_the_same(client):
    body = _resolve_raw(client, "1.2mm thick double bowl kitchen sink")
    codes = _spec_codes(body)
    assert codes and codes[0] == "ZZTKS12"


def test_the_other_thickness_flips_the_answer(client):
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.0mm")
    codes = _spec_codes(body)
    assert codes and codes[0] == "ZZTKS10"


def test_explicit_caller_fields_still_win(client):
    # A caller that DID extract keeps its reading: explicit beats derived.
    body = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink with thickness 1.2mm",
            "spec_fallback": True,
            "extracted_specs": [{"key": "thickness", "value": 1.0}],
        },
    ).json()
    codes = _spec_codes(body)
    assert codes and codes[0] == "ZZTKS10"


def test_without_the_flag_nothing_changes(client):
    body = client.post(RESOLVE, json={"query": "double bowl kitchen sink"}).json()
    assert "spec_candidates" not in body


# --------------------------------------------------------------------------- #
# parity: resolve's reading IS the preview page's reading                       #
# --------------------------------------------------------------------------- #
def test_resolve_and_preview_read_the_same_sentence_identically(client):
    sentence = "double bowl kitchen sink with thickness 1.2mm"
    via_resolve = _resolve_raw(client, sentence)
    via_preview = client.post(PREVIEW, json={"phrase": sentence, "understand": False}).json()

    resolve_codes = _spec_codes(via_resolve)
    preview_codes = [c["product_code"] for c in via_preview["candidates"]]
    assert resolve_codes == preview_codes
    assert [c["score"] for c in via_resolve["spec_candidates"]] == [
        c["score"] for c in via_preview["candidates"]
    ]
