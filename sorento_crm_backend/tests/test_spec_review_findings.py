"""The ten review findings on `feat/spec-raw-text-search`, pinned as behaviour.

Each group is named for the finding it closes, so a regression names itself:

  F1  a refusal in the customer's own words is a refusal, deterministically
  F2  a miss is cleared only when the answer actually answered it
  F3  a spec entry with no `key` is bad input, never a 500
  F4  a term that bound something can still contain an alien WORD
  F5  code-shaped means what the resolver means by it (B2155, S7850, 10KG)
  F6  the honesty fields speak only when the turn is product-descriptive
  F7  a caller's own term is checked word by word too
  F8  a customer naming an excluded brand IN FULL is asking for it
  F9  require-only rows carry their spec values like every other row
  F10 one derivation helper, shared by resolve and preview

Postgres only, blank schema, ZZT-prefixed rows, every chain seeded here
(standing rules). Plan: documentation/plans/PLAN-spec-raw-text-search.md.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Stock, Warehouse
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session

RESOLVE = "/api/v1/system/references/resolve"
PREVIEW = "/api/v1/master-data/product-specifications/preview-search"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}


def _product(db, code, description, *, brand=None, derive: bool = True):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=db.info["cat"],
        brand_id=db.info[brand] if brand else None,
        base_uom_id=db.info["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    if derive:
        derive_for_code(db, code)
    return row


def _seed_user(db):
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
    db.add_all([role, user])
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        # The two placeholders the registry marks `excluded_values`: one is a full
        # two-word phrase a customer can genuinely say, the other is a single
        # generic word (F8).
        no_logo = Brand(id=str(uuid.uuid4()), brand_code="ZZT-NL", brand_name="NO LOGO")
        others = Brand(id=str(uuid.uuid4()), brand_code="ZZT-OT", brand_name="OTHERS")
        s.add_all([cat, uom, sorento, no_logo, others])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        s.info.update(
            {
                "cat": cat.id,
                "uom": uom.id,
                "sorento": sorento.id,
                "no_logo": no_logo.id,
                "others": others.id,
            }
        )
        _seed_user(s)
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


def _resolve(client, sentence, **extra) -> dict:
    return client.post(
        RESOLVE, json={"query": sentence, "spec_fallback": True, **extra}
    ).json()


def _spec_codes(body: dict) -> list[str]:
    return [c["product_code"] for c in body.get("spec_candidates") or []]


@pytest.fixture()
def sinks(db):
    """Two sinks that differ only in material, plus one with a drainer board."""
    _product(
        db,
        "ZZTKSGL",
        "SORENTO GLASS KITCHEN SINK SINGLE BOWL (820X450X230X1.2MM)",
        brand="sorento",
    )
    _product(
        db,
        "ZZTKSSS",
        "SORENTO S/STEEL KITCHEN SINK SINGLE BOWL (820X450X230X1.2MM)",
        brand="sorento",
    )
    return db


# =========================================================================== #
# F1 - a refusal the customer wrote in plain words                             #
# =========================================================================== #
def test_f1_a_refused_material_becomes_an_exclusion_without_a_model(db):
    from app.services.product_spec_understanding import understand_phrase

    understanding = understand_phrase(db, "kitchen sink, not glass", allow_model=False)
    assert {"key": "material", "value": "glass"} in understanding.exclusions
    assert not [e for e in understanding.specs if e["key"] == "material"]


def test_f1_a_refused_material_is_not_offered(client, sinks):
    body = _resolve(client, "kitchen sink, not glass")
    codes = _spec_codes(body)
    assert "ZZTKSGL" not in codes, codes
    assert "ZZTKSSS" in codes, codes


def test_f1_without_drainer_refuses_the_drainer_board(client, db):
    _product(
        db,
        "ZZTKSDR",
        "SORENTO S/STEEL KITCHEN SINK WITH DRAINER (820X450X230X1.2MM)",
        brand="sorento",
    )
    _product(
        db,
        "ZZTKSND",
        "SORENTO S/STEEL KITCHEN SINK SINGLE BOWL (820X450X230X1.2MM)",
        brand="sorento",
    )
    body = _resolve(client, "kitchen sink without drainer")
    codes = _spec_codes(body)
    assert "ZZTKSDR" not in codes, codes
    assert "ZZTKSND" in codes, codes


def test_f1_a_plain_material_word_still_binds_positively(client, sinks):
    body = _resolve(client, "glass kitchen sink")
    codes = _spec_codes(body)
    assert codes and codes[0] == "ZZTKSGL", codes


def test_f1_a_brand_phrase_that_starts_with_no_is_not_a_refusal(db):
    from app.services.product_spec_understanding import understand_phrase

    understanding = understand_phrase(db, "no logo kitchen sink", allow_model=False)
    assert understanding.exclusions == []
    assert {"key": "brand", "value": "NO LOGO"} in understanding.specs


# =========================================================================== #
# F2 - a miss is cleared only by an answer that actually answered it           #
# =========================================================================== #
@pytest.fixture()
def described_sinks(db):
    _product(
        db,
        "ZZTKS2B",
        "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        brand="sorento",
    )
    _product(
        db,
        "ZZTKS1B",
        "SORENTO S/STEEL SINGLE BOWL KITCHEN SINK (860X500X200X1.0MM)",
        brand="sorento",
    )
    return db


def test_f2_the_answered_description_is_still_cleared(client, described_sinks):
    body = client.post(
        RESOLVE,
        json={
            "query": "sorento double bowl kitchen sink",
            "tokens": ["Sorento", "double bowl kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates")
    assert "double bowl kitchen sink" not in (body.get("unresolved_tokens") or [])


def test_f2_a_second_unanswered_description_survives(client, described_sinks):
    body = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink and a bathroom mirror",
            "tokens": ["double bowl kitchen sink", "bathroom mirror"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates")
    unresolved = body.get("unresolved_tokens") or []
    assert "double bowl kitchen sink" not in unresolved
    assert "bathroom mirror" in unresolved, unresolved


def test_f2_an_unanswered_company_name_survives(client, described_sinks):
    body = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink from ACME trading",
            "tokens": ["double bowl kitchen sink", "ACME trading"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates")
    assert "ACME trading" in (body.get("unresolved_tokens") or [])


# =========================================================================== #
# F3 - a spec entry with no key is bad input, never a 500                      #
# =========================================================================== #
def test_f3_a_spec_entry_without_a_key_still_answers(client, described_sinks):
    response = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink",
            "spec_fallback": True,
            "extracted_specs": [{"value": 1.2}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json().get("spec_candidates")


# =========================================================================== #
# F4 - a term that bound something can still contain an alien WORD             #
# =========================================================================== #
def test_f4_a_mixed_term_reports_its_alien_word(db):
    from app.services.product_spec_search import filter_specs

    verdict = filter_specs(db, free_terms=["sorento grommet"])
    assert verdict["unrecognized_terms"] == ["grommet"]


def test_f4_a_fully_known_term_reports_nothing(db):
    from app.services.product_spec_search import filter_specs

    verdict = filter_specs(db, free_terms=["kitchen sink"])
    assert verdict["unrecognized_terms"] == []


def test_f4_an_all_alien_term_is_still_reported_verbatim(db):
    from app.services.product_spec_search import filter_specs

    verdict = filter_specs(db, free_terms=["flurbish grommet"])
    assert verdict["unrecognized_terms"] == ["flurbish grommet"]


# =========================================================================== #
# F5 - code-shaped means what the resolver means by it                         #
# =========================================================================== #
@pytest.mark.parametrize("code", ["B2155", "S7850", "ACC-SRT1024"])
def test_f5_a_resolver_shaped_code_stays_in_unresolved_tokens(
    client, described_sinks, code
):
    body = client.post(
        RESOLVE,
        json={
            "query": f"{code} kitchen sink",
            "tokens": [code, "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates"), "the description must still reach the ranker"
    assert code in (body.get("unresolved_tokens") or [])


# "10KG" is a number carrying a unit, so the measurement guard claims it before
# the code test ever runs. The resolver's own comment lists it as a code shape,
# and both readings are defensible - a unit-suffixed number is the one that
# cannot invent a failure, so it wins here (F5).
@pytest.mark.parametrize("measurement", ["1.2mm", "2mm", "750MM", "10KG"])
def test_f5_a_measurement_is_never_code_shaped(client, described_sinks, measurement):
    body = client.post(
        RESOLVE,
        json={
            "query": f"{measurement} kitchen sink",
            "tokens": [measurement, "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates")
    assert measurement not in (body.get("unresolved_tokens") or [])


# =========================================================================== #
# F6 - the honesty fields speak only for a product-descriptive turn            #
# =========================================================================== #
def test_f6_a_person_name_turn_admits_no_unrecognized_terms(client, described_sinks):
    body = _resolve(client, "quotation for Encik Baharudin")
    assert body.get("spec_candidates") in (None, [])
    # The field stays on the wire (contract), it just has nothing honest to say.
    assert body.get("unrecognized_terms") == []


def test_f6_the_name_token_is_still_reported_as_unresolved(client, described_sinks):
    body = client.post(
        RESOLVE,
        json={
            "query": "quotation for Encik Baharudin",
            "tokens": ["Encik Baharudin"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert "Encik Baharudin" in (body.get("unresolved_tokens") or [])


def test_f6_a_descriptive_turn_still_reports_its_alien_word(client, described_sinks):
    body = _resolve(client, "double bowl kitchen sink with flurbish")
    assert body.get("unrecognized_terms") == ["flurbish"]


# =========================================================================== #
# F7 - a caller's own term is checked word by word too                         #
# =========================================================================== #
def test_f7_a_caller_term_reports_only_its_alien_word(db):
    from app.services.product_spec_search import unrecognized_terms

    assert unrecognized_terms(db, query="", free_terms=["sink flurbish"]) == ["flurbish"]


def test_f7_an_all_alien_caller_term_stays_verbatim(db):
    from app.services.product_spec_search import unrecognized_terms

    assert unrecognized_terms(db, query="", free_terms=["flurbish grommet"]) == [
        "flurbish grommet"
    ]


# =========================================================================== #
# F8 - naming an excluded brand IN FULL is a real ask                          #
# =========================================================================== #
@pytest.fixture()
def unbranded_and_branded(db):
    _product(
        db,
        "ZZTKSNL",
        "NO LOGO S/STEEL KITCHEN SINK SINGLE BOWL (820X450X230X1.2MM)",
        brand="no_logo",
    )
    _product(
        db,
        "ZZTKSSR",
        "SORENTO S/STEEL KITCHEN SINK SINGLE BOWL (860X500X200X1.0MM)",
        brand="sorento",
    )
    _product(
        db,
        "ZZTKSOT",
        "OTHERS S/STEEL KITCHEN SINK SINGLE BOWL (900X500X200X1.0MM)",
        brand="others",
    )
    return db


def test_f8_a_full_excluded_brand_phrase_binds(db, unbranded_and_branded):
    from app.services.product_spec_search import resolve_terms_to_specs

    entries = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["no logo kitchen sink"])}
    assert entries.get("brand") == "NO LOGO"


def test_f8_the_named_brand_ranks_first(client, unbranded_and_branded):
    body = _resolve(client, "no logo kitchen sink")
    candidates = body.get("spec_candidates") or []
    assert candidates and candidates[0]["product_code"] == "ZZTKSNL", candidates
    # First BECAUSE the brand was heard, not because its code sorts earliest.
    assert "brand" in candidates[0]["matched_specs"], candidates[0]


def test_f8_a_generic_excluded_brand_word_binds_nothing(db, unbranded_and_branded):
    from app.services.product_spec_search import resolve_terms_to_specs

    entries = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["others kitchen sink"])}
    assert "brand" not in entries


def test_f8_the_generic_word_is_not_reported_as_unknown_either(
    client, unbranded_and_branded
):
    body = _resolve(client, "others kitchen sink")
    assert body.get("unrecognized_terms") == []


# =========================================================================== #
# F9 - require-only rows carry their spec values                               #
# =========================================================================== #
def _stock(db, product, qty):
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"ZZT-{uuid.uuid4().hex[:6]}",
        warehouse_name="ZZT WH",
    )
    db.add(wh)
    db.flush()
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=product.id,
            warehouse_id=wh.id,
            quantity_on_hand=qty,
            quantity_reserved=0,
            quantity_damaged=0,
        )
    )
    db.flush()


def test_f9_a_require_only_row_shows_its_spec_values(db):
    from app.services.product_predicate_service import resolve_product_set

    described = _product(
        db,
        "ZZTKSRQ",
        "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        brand="sorento",
    )
    _stock(db, described, 3)
    out = resolve_product_set(db, require={"stock": True})
    row = next(c for c in out["candidates"] if c["product_code"] == "ZZTKSRQ")
    assert row["specifications"], row
    assert row["specifications"].get("class") == "Kitchen Sink"
    assert row["preferred_specs"] == []


def test_f9_a_row_with_no_spec_block_says_so(db):
    from app.services.product_predicate_service import resolve_product_set

    bare = _product(db, "ZZTKSBARE", "SORENTO MYSTERY ITEM", derive=False)
    _stock(db, bare, 1)
    out = resolve_product_set(db, require={"stock": True})
    row = next(c for c in out["candidates"] if c["product_code"] == "ZZTKSBARE")
    # Null, not {}: the frozen contract reads absent as "not recorded".
    assert row["specifications"] is None, row


# =========================================================================== #
# F10 - one derivation helper, shared by resolve and preview                   #
# =========================================================================== #
def test_f10_both_endpoints_call_the_shared_helper(client, described_sinks, monkeypatch):
    from app.services import product_spec_understanding as understanding_module

    calls: list[dict] = []
    real = understanding_module.derive_search_inputs

    def spy(db, phrase, **kwargs):
        calls.append({"phrase": phrase, **kwargs})
        return real(db, phrase, **kwargs)

    monkeypatch.setattr(understanding_module, "derive_search_inputs", spy)

    sentence = "double bowl kitchen sink with thickness 1.2mm"
    client.post(RESOLVE, json={"query": sentence, "spec_fallback": True})
    client.post(PREVIEW, json={"phrase": sentence, "understand": False})

    assert len(calls) == 2, calls
    assert {call["phrase"] for call in calls} == {sentence}


def test_f10_resolve_names_the_acting_caller(client, described_sinks, monkeypatch):
    from app.services import product_spec_understanding as understanding_module

    seen: list = []
    real = understanding_module.derive_search_inputs

    def spy(db, phrase, **kwargs):
        seen.append(kwargs.get("user_id"))
        return real(db, phrase, **kwargs)

    monkeypatch.setattr(understanding_module, "derive_search_inputs", spy)
    client.post(
        RESOLVE,
        json={"query": "double bowl kitchen sink", "spec_fallback": True},
    )
    assert seen == [_USER["id"]]
