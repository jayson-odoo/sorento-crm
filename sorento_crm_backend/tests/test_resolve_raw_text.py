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

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
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


# --------------------------------------------------------------------------- #
# spec_top_score: "there is nothing" is a different answer from "nothing        #
# cleared the bar", and floor_missed cannot tell the two apart                  #
# --------------------------------------------------------------------------- #
# `floor_missed` is true for both, and the candidate list is emptied either way,
# so a renderer holding only the bool prints "I found near misses but nothing I
# would stand behind" on a turn where nothing scored at all. That sentence is a
# claim about the catalogue that never happened, which is the exact class of
# dishonesty the honesty fields exist to prevent.
NONSENSE = "flurbish quantum toaster"
SINK = "double bowl kitchen sink with thickness 1.2mm"


def _floor(db) -> float:
    from app.services.product_spec_registry import search_policy

    return search_policy(db)["relevance_floor"]


def _raise_the_floor(db, value: float) -> None:
    from app.models.product_spec import ProductSpecSearchPolicy
    from app.services.product_spec_registry import seed_search_policy

    seed_search_policy(db)
    db.query(ProductSpecSearchPolicy).filter_by(policy_key="relevance_floor").one().value = value
    db.flush()


def _prefer_the_house_brand(db, bonus: float) -> None:
    from app.models.product_spec import ProductSpecRegistry

    db.query(ProductSpecRegistry).filter_by(spec_key="brand").one().value_weights = {
        "sorento": bonus
    }
    db.flush()


def _house_branded_sink(db) -> None:
    """A row a house preference can actually land on.

    `brand` is derived off the product's own `brand_id`, never off the words in
    its description (the prefix read got 1,934 rows wrong and was removed), so
    the shared fixture's rows carry no brand value at all and a preference keyed
    on one would be inert - a test that cannot fail. Its description matches the
    1.2mm sink's word for word, so the two earn identical EVIDENCE and only the
    preference separates their totals.
    """
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
    db.add(brand)
    db.flush()
    row = Product(
        id=str(uuid.uuid4()),
        product_code="ZZTKSHOUSE",
        product_name="ZZTKSHOUSE",
        description="SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=brand.id,
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    derive_for_code(db, "ZZTKSHOUSE")


def test_a_true_zero_turn_reports_no_evidence_at_all(client):
    body = _resolve_raw(client, NONSENSE)

    assert body["floor_missed"] is True
    assert body["spec_candidates"] == []
    # Nothing scored, so there is nothing to be near.
    assert body["spec_top_score"] == 0.0


def test_a_turn_that_answers_reports_the_evidence_it_earned(client, db):
    body = _resolve_raw(client, SINK)

    assert body["floor_missed"] is False
    assert body["spec_candidates"]
    assert body["spec_top_score"] >= _floor(db)


def test_a_near_miss_keeps_its_evidence_after_the_list_is_emptied(client, db):
    # The BAR is moved rather than the sentence weakened. What a sentence earns
    # moves with the catalogue and with every scoring knob, so a phrase picked
    # today for landing just under the floor stops being a near miss silently -
    # and the test would still pass, having become a second true-zero case. To
    # the code under test the two are the same event: evidence on one side of the
    # comparison, the floor on the other.
    before = _resolve_raw(client, SINK)
    _raise_the_floor(db, before["spec_top_score"] + 1.0)
    after = _resolve_raw(client, SINK)

    assert after["floor_missed"] is True
    assert after["spec_candidates"] == []
    # The verdict changed and the quantity did not. That is the whole field: the
    # shortlist is gone and it can still say something was there.
    assert after["spec_top_score"] == before["spec_top_score"]
    assert after["spec_top_score"] > 0.0


@pytest.mark.parametrize(
    "sentence",
    [NONSENSE, SINK, "1.2mm thick double bowl kitchen sink", "kitchen sink"],
)
def test_the_verdict_is_exactly_the_field_read_against_the_floor(client, db, sentence):
    body = _resolve_raw(client, sentence)

    assert "floor_missed" in body, "the spec path must have run for this to mean anything"
    assert body["floor_missed"] is (body["spec_top_score"] < _floor(db))


def test_a_house_preference_alone_is_never_reported_as_evidence(client, db):
    """A preference can reorder answers; it cannot BE one, or be a near miss.

    The total score carries the house preference, and 8.0 sits above a floor of
    1.5 on its own. Reporting the total here would tell the renderer that a
    greeting nearly found something, on a turn where the customer's own words
    earned nothing at all - the same bug the floor was moved onto evidence to
    kill, rebuilt in a new field.
    """
    _house_branded_sink(db)
    _prefer_the_house_brand(db, 8.0)

    body = _resolve_raw(client, NONSENSE)

    assert body["floor_missed"] is True
    assert body["spec_top_score"] == 0.0


def test_the_field_is_the_evidence_and_not_the_total_score(client, db):
    _house_branded_sink(db)
    _prefer_the_house_brand(db, 8.0)

    body = _resolve_raw(client, SINK)

    assert body["spec_candidates"]
    best_total = max(c["score"] for c in body["spec_candidates"])
    # The house-branded row rides 8.0 it did not earn, so the two numbers cannot
    # be the same one. Without this, a later refactor could hand `top_score` to
    # the field and every other test in this section would still pass.
    assert best_total >= body["spec_top_score"] + 8.0
