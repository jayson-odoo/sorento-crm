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

from app.models.base import company_scope
from app.models.company import Company
from app.models.marketing import Promotion
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session, unique_code

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


def test_partial_code_overlap_does_not_suppress_the_fallback(db, client):
    """SA-P1: this catalog writes description words INTO product codes
    (SRTWB7104-WALL HUNG), so an AND-mode turn like "wall hung basin" collects
    partial code matches - the words "wall hung" literally appear in codes - 
    and the zero-match gate then never fires, for exactly the phrase class the
    fallback exists to answer. "Partially matched a code" is not "the
    description was answered": the gate must also fire when no returned
    product row covered EVERY word.
    """
    spare = Product(
        id=str(uuid.uuid4()),
        product_code="ZZT-KITCHEN SINK-BKT",
        product_name="ZZT-KITCHEN SINK-BKT",
        description="TRIANGLE BASKET SPARE",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(spare)
    db.flush()
    derive_for_code(db, spare.product_code)

    body = client.post(
        ENDPOINT,
        json={
            "query": "stainless steel kitchen sink",
            "tokens": ["stainless steel kitchen sink"],
            "match_mode": "and",
            "spec_fallback": True,
            "extracted_specs": [
                {"key": "class", "value": "Kitchen Sink"},
                {"key": "material", "value": "stainless_steel"},
            ],
            "free_terms": ["kitchen sink"],
        },
    ).json()

    assert "spec_candidates" in body, "partial code coverage must not suppress spec search"
    spec_matches = [
        m
        for r in body.get("resolutions", [])
        for m in r.get("matches", [])
        if m.get("match_tier") == "spec_search"
    ]
    assert "ZZTKS9001" in [m["canonical_code"] for m in spec_matches]
    # The AND views were REPLACED by the ranked answer, not left describing
    # the partial code overlap.
    if "intersection" in body:
        assert all(m.get("match_tier") == "spec_search" for m in body["intersection"])


def test_full_code_coverage_still_suppresses_the_fallback(db, client):
    """The counterweight: when a returned product row DOES cover every word, the
    description was answered by codes and spec search must stay out of the way.
    Same catalog quirk as above - the words all appear in the code - but this
    time the overlap is COMPLETE, which is the case max-coverage is right about.
    """
    spare = Product(
        id=str(uuid.uuid4()),
        product_code="ZZT-KITCHEN SINK-BKT",
        product_name="ZZT-KITCHEN SINK-BKT",
        description="TRIANGLE BASKET SPARE",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(spare)
    db.flush()
    derive_for_code(db, spare.product_code)

    body = client.post(
        ENDPOINT,
        json={
            "query": "kitchen sink",
            "tokens": ["kitchen sink"],
            "match_mode": "and",
            "spec_fallback": True,
            "free_terms": ["kitchen sink"],
        },
    ).json()

    assert [m["canonical_code"] for m in body.get("intersection", [])] == ["ZZT-KITCHEN SINK-BKT"]
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

    It is a different shape parked beside the result, so every existing consumer - the
    n8n spine's resolve-entity, and get-results behind it - read `resolutions[].matches`,
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


# --------------------------------------------------------------------------- #
# a product question answered only by promotions is not answered (#338)         #
# --------------------------------------------------------------------------- #
# Exec 14061515's request, as the n8n spine sent it: one category-hinted token,
# the parser's `inventory` domain, the AND-then-fallback flags. `understand_phrase`
# is left off: that half is the model read, and the word-level read alone decides
# what the gate sees.
TURN_14061515 = {
    "query": "any water closet s trap 250mm got stock?",
    "tokens": ["water closet s trap 250mm"],
    "match_mode": "and",
    "allowed_entity_types": ["category"],
    "domain": "inventory",
    "fallback_to_all_types": True,
    "limit": 15,
    "spec_fallback": True,
}
MOCHA_ID = "00000000-0000-0000-0000-000000000002"


def _water_closet(db, code, description, *, category, company_id=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=category,
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _all_matches(body: dict) -> list[dict]:
    """Every row the caller was shown, whichever shape the resolver answered in."""
    if "intersection" in body:
        return list(body["intersection"])
    return [m for tr in body.get("resolutions") or [] for m in tr.get("matches") or []]


@pytest.fixture
def water_closet_catalogue(db):
    """The catalogue behind exec 14061515: eleven promotions whose description
    carries the customer's words, and the water closets that answer the question
    but which the code probes cannot see (they are CODE-ONLY by design)."""
    wc_cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC")
    db.add(wc_cat)
    db.flush()
    backfill_category_signals(db)
    for n in range(1, 12):
        db.add(
            Promotion(
                id=str(uuid.uuid4()),
                description=f"SORENTO WATER CLOSET PROMO_2026_{n:02d}.pdf",
                is_active=True,
            )
        )
    db.flush()
    wanted = _water_closet(
        db, "ZZTWC250S", "SORENTO WATER CLOSET S-TRAP 250MM (680X370X760MM)", category=wc_cat.id
    )
    _water_closet(
        db, "ZZTWC300S", "SORENTO WATER CLOSET S-TRAP 300MM (680X370X760MM)", category=wc_cat.id
    )
    _water_closet(
        db, "ZZTWC180P", "SORENTO WATER CLOSET P-TRAP 180MM (680X370X760MM)", category=wc_cat.id
    )
    return {"category": wc_cat.id, "wanted": wanted.id}


@pytest.fixture()
def turn_14061515(client, water_closet_catalogue) -> dict:
    return client.post(ENDPOINT, json=TURN_14061515).json()


def test_the_probes_found_promotions_and_no_product(client, water_closet_catalogue):
    """Guard the guard: the replay has to reproduce the bug's shape. If the token
    had matched nothing, the tests below would pass through the zero-match gate
    and prove nothing about a token that promotions "answered". Read with the
    flag off, because with it on the ranker's rows replace what the probes found.
    """
    body = client.post(ENDPOINT, json={**TURN_14061515, "spec_fallback": False}).json()

    types = {m["entity_type"] for m in _all_matches(body)}
    assert "promotion" in types
    assert "product" not in types


@pytest.mark.parametrize(
    "shape",
    [
        # AND: one intersection, the shape this fixture's replay takes.
        {"intersection": [{"entity_type": "promotion"}]},
        # OR: per-token resolutions, the shape live exec 14061515 took after the
        # AND-to-OR rewrite. One token answered by a product does not clear
        # another answered only by a promotion.
        {
            "resolutions": [
                {"token": "ZZTKS9001", "matches": [{"entity_type": "product"}]},
                {"token": "water closet", "matches": [{"entity_type": "promotion"}]},
            ]
        },
    ],
)
@pytest.mark.parametrize("domain", ["inventory", "master_products", "product_attachment"])
def test_the_rule_reads_both_answer_shapes(shape, domain):
    from app.api.v1.system.references import _no_product_row_answered

    assert _no_product_row_answered(shape, domain) is True
    assert _no_product_row_answered(shape, "promotion") is False
    assert _no_product_row_answered(shape, "") is False
    assert _no_product_row_answered(shape, None) is False


@pytest.mark.parametrize("row_type", ["product", "product_set"])
def test_a_product_row_of_either_kind_answers(row_type):
    from app.api.v1.system.references import _no_product_row_answered

    answered = {"intersection": [{"entity_type": row_type}, {"entity_type": "promotion"}]}
    assert _no_product_row_answered(answered, "inventory") is False
    answered = {"resolutions": [{"token": "x", "matches": [{"entity_type": row_type}]}]}
    assert _no_product_row_answered(answered, "inventory") is False


def test_an_inventory_question_answered_only_by_promotions_reaches_the_ranker(
    turn_14061515, water_closet_catalogue
):
    assert turn_14061515.get("spec_candidates"), "a promotion is not stock: the spec gate must fire"
    assert turn_14061515["floor_missed"] is False
    assert turn_14061515["spec_candidates"][0]["product_id"] == water_closet_catalogue["wanted"]
    asked = {entry["key"] for entry in turn_14061515["spec_asked"]}
    assert {"trap_type", "trap_length"} <= asked


def test_the_water_closet_arrives_as_an_ordinary_product_match(turn_14061515, water_closet_catalogue):
    spec_rows = [m for m in _all_matches(turn_14061515) if m.get("match_tier") == "spec_search"]
    assert water_closet_catalogue["wanted"] in [m["uuid"] for m in spec_rows]


@pytest.mark.parametrize("domain", ["promotion", ""])
def test_the_same_token_outside_a_product_domain_is_untouched(
    client, water_closet_catalogue, domain
):
    """A promotion question IS answered by a promotion, and a request that names
    no domain gives the gate nothing to decide on: both keep today's response."""
    body = client.post(ENDPOINT, json={**TURN_14061515, "domain": domain}).json()

    assert "spec_candidates" not in body
    assert "spec_asked" not in body
    assert {m["entity_type"] for m in _all_matches(body)} >= {"promotion"}
    assert not [m for m in _all_matches(body) if m.get("match_tier") == "spec_search"]


def test_the_relevance_floor_still_refuses_nonsense(client, water_closet_catalogue):
    body = client.post(
        ENDPOINT,
        json={
            **TURN_14061515,
            "query": "any purple levitating sink got stock?",
            "tokens": ["purple levitating sink"],
        },
    ).json()

    assert body["floor_missed"] is True
    assert body["spec_candidates"] == []


def test_the_answer_is_company_scoped(db, client, water_closet_catalogue):
    """Another company's water closet with the same spec must not be offered to
    a Sorento contact.

    A DIFFERENT code on purpose: `search_specs` collapses rows sharing a code
    into one family, so a leaked same-code row would hide behind Sorento's and
    the assertion could never fail. Seeded under the all-companies scope, which
    is also how the assertion is proved falsifiable: with scope off the row IS
    offered.
    """
    with company_scope(db, None):
        db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        db.flush()
        mocha = _water_closet(
            db,
            "ZZTWC251S",
            "SORENTO WATER CLOSET S-TRAP 250MM (680X370X760MM)",
            category=water_closet_catalogue["category"],
            company_id=MOCHA_ID,
        )
        leaked = client.post(ENDPOINT, json=TURN_14061515).json()
    assert mocha.id in [c["product_id"] for c in leaked["spec_candidates"]], (
        "with no scope the row must show, or the scoped assertion below proves nothing"
    )

    body = client.post(ENDPOINT, json=TURN_14061515).json()

    offered = [c["product_id"] for c in body["spec_candidates"]]
    assert water_closet_catalogue["wanted"] in offered
    assert mocha.id not in offered
