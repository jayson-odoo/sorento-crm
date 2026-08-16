"""Hardening pass over S1-S4 of spec-raw-text-search: the edges the slice tests
did not pin.

Five groups, each traced to the plan's acceptance criteria
(`documentation/plans/PLAN-spec-raw-text-search.md`):

  1. Param validation + auth denial on `GET /master-data/products`
     (`include_specifications`).
  2. The `include_specifications=true` listing at a page boundary: every row
     carries the block, and attaching it costs exactly one extra query.
  3. `_emit_spec_matches`'s code-exemption boundary: a real code that resolves
     never reaches `unresolved_tokens`; a made-up code stays; a measurement
     token and an `L750`-style label are cleared once the sentence around them
     is answered.
  4. Bilingual class words (`CLASS_SYNONYMS` in `product_class_signal.py`) are
     never reported as unrecognized.
  5. The two live incident turns (12303509, 12303548), replayed as endpoint
     tests, with the honesty fields (`spec_asked`, `spec_unmet`,
     `unrecognized_terms`) and the display block asserted together.

Postgres only, blank schema per test file, ZZT-prefixed rows, nothing borrowed
(standing rules).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_search import unrecognized_words
from tests._pg_fixture import blank_session

RESOLVE = "/api/v1/system/references/resolve"
PRODUCTS = "/api/v1/master-data/products/"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}


def _product(db, code, description, *, category, brand_id=None, derive: bool = True):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=category,
        brand_id=brand_id,
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
        sink_cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"
        )
        wc_cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC"
        )
        junk_cat = ProductCategory(
            id=str(uuid.uuid4()), category_code="SRT-ACC", category_name="SRT-ACC"
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        s.add_all([sink_cat, wc_cat, junk_cat, uom, sorento])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        s.info["uom"] = uom.id
        s.info["sink_cat"] = sink_cat.id
        s.info["wc_cat"] = wc_cat.id
        s.info["junk_cat"] = junk_cat.id
        s.info["sorento"] = sorento.id
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


def _resolve(client, **payload) -> dict:
    body = {"spec_fallback": True, **payload}
    return client.post(RESOLVE, json=body).json()


def _codes_in_resolutions(body: dict) -> list[str]:
    return [
        str(m.get("canonical_code") or "")
        for tr in body.get("resolutions") or []
        for m in tr.get("matches") or []
    ]


def _all_spec_matches(body: dict) -> list[dict]:
    """Every spec-tier match across every resolution, not just the first."""
    return [
        m
        for tr in body.get("resolutions") or []
        for m in tr.get("matches") or []
        if m.get("match_tier") == "spec_search"
    ]


# =========================================================================== #
# 1. Param validation + auth denial on the products listing                     #
# =========================================================================== #
def test_include_specifications_rejects_a_non_boolean(client):
    response = client.get(PRODUCTS, params={"include_specifications": "banana"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert any(
        err.get("loc") == ["query", "include_specifications"] for err in body["detail"]
    )


def test_products_listing_denies_the_unauthenticated_caller():
    # No dependency overrides, no Bearer token, no X-API-Key -> 401/403, same
    # pattern as test_product_neighbours.test_neighbours_endpoint_requires_auth.
    from app.main import app

    with TestClient(app) as anon_client:
        response = anon_client.get(
            PRODUCTS, params={"include_specifications": "true"}
        )
    assert response.status_code in (401, 403), response.text


# =========================================================================== #
# 2. include_specifications=true at a page boundary                             #
# =========================================================================== #
def test_every_row_on_a_boundary_page_carries_the_block(db, client):
    for i in range(5):
        _product(
            db,
            f"ZZTPG{i}",
            f"SORENTO KITCHEN SINK PAGE TEST {i} (100X100X100X1.{i}MM)",
            category=db.info["sink_cat"],
            brand_id=db.info["sorento"],
        )

    response = client.get(
        PRODUCTS,
        params={
            "query": "ZZTPG",
            "limit": 2,
            "page": 2,
            "sort": "product_code",
            "dir": "asc",
            "include_specifications": "true",
        },
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 2, rows
    for row in rows:
        assert "specifications" in row
        block = row["specifications"]
        # Every seeded row here was derived, so the block is populated, not null.
        assert block is not None
        assert isinstance(block["values"], dict) and block["values"]


def test_attaching_specifications_costs_exactly_one_extra_query(db, client):
    for i in range(5):
        _product(
            db,
            f"ZZTPQ{i}",
            f"SORENTO KITCHEN SINK QCOUNT TEST {i} (100X100X100X1.{i}MM)",
            category=db.info["sink_cat"],
            brand_id=db.info["sorento"],
        )

    statements: list[str] = []

    def record(conn, cursor, statement, params, context, executemany):
        if "product_specifications" in statement.lower():
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        response = client.get(
            PRODUCTS,
            params={
                "query": "ZZTPQ",
                "limit": 2,
                "page": 2,
                "sort": "product_code",
                "dir": "asc",
                "include_specifications": "true",
            },
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)

    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 2
    # ONE query for the whole page (an IN over the ids already fetched), not one
    # per row - the product_service.specifications_for_products contract.
    assert len(statements) == 1, statements


# =========================================================================== #
# 3. _emit_spec_matches code-exemption boundaries                               #
# =========================================================================== #
def test_a_real_code_that_resolves_never_reaches_unresolved_tokens(client, db):
    real = _product(
        db,
        "ZZTKSREAL",
        "SORENTO KITCHEN SINK REAL CODE (100X100X100X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    body = client.post(
        RESOLVE,
        json={
            "query": "ZZTKSREAL",
            "tokens": ["ZZTKSREAL"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert "ZZTKSREAL" not in (body.get("unresolved_tokens") or [])
    assert "ZZTKSREAL" in _codes_in_resolutions(body)


def test_a_made_up_code_stays_in_unresolved_tokens(client, db):
    _product(
        db,
        "ZZTKS2B",
        "SORENTO KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    body = client.post(
        RESOLVE,
        json={
            # A digit is load-bearing: _is_code_shaped requires one, so a made-up
            # code without one (e.g. "ZZTKSGHOST") reads as a description word
            # instead - this is the digit-carrying shape a real stale/typo'd
            # code actually has.
            "query": "ZZTKS404 kitchen sink",
            "tokens": ["ZZTKS404", "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates"), "the description must still reach the ranker"
    assert "ZZTKS404" in (body.get("unresolved_tokens") or [])


@pytest.mark.parametrize("measurement_token", ["1.2mm", "2mm"])
def test_a_measurement_token_is_cleared_not_reported_as_a_missing_code(
    client, db, measurement_token
):
    _product(
        db,
        "ZZTKS12",
        "SORENTO KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    body = client.post(
        RESOLVE,
        json={
            "query": f"{measurement_token} kitchen sink",
            "tokens": [measurement_token, "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates"), "the description must still reach the ranker"
    assert measurement_token not in (body.get("unresolved_tokens") or [])


def test_an_l750_style_label_is_cleared(client, db):
    _product(
        db,
        "ZZTKS12",
        "SORENTO KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    body = client.post(
        RESOLVE,
        json={
            "query": "L750 kitchen sink",
            "tokens": ["L750", "kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()
    assert body.get("spec_candidates"), "the description must still reach the ranker"
    assert "L750" not in (body.get("unresolved_tokens") or [])


# =========================================================================== #
# 4. Malay/bilingual class words are never unrecognized                        #
# =========================================================================== #
def test_sinki_is_a_known_class_word(db):
    # "sinki" is a CLASS_SYNONYMS entry for Kitchen Sink (SRT-KS backfilled above).
    assert unrecognized_words(db, "sinki") == []


def test_tandas_is_a_known_class_word(db):
    # "tandas" is a CLASS_SYNONYMS entry for Water Closet (SRT-WC backfilled above).
    assert unrecognized_words(db, "tandas") == []


def test_a_bilingual_sentence_admits_nothing(db):
    # Only catalogue-known words: two Malay class synonyms back to back must not
    # trip each other up.
    assert unrecognized_words(db, "sinki tandas") == []


# =========================================================================== #
# 5. The two live incident turns, endpoint level                                #
# =========================================================================== #
@pytest.fixture()
def turn_a_seed(db):
    """The live 12303509 catalogue shape: a described sink plus brand-prefixed junk."""
    _product(
        db,
        "ZZTKS2B",
        "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    _product(
        db,
        "ZZTKS1B",
        "SORENTO S/STEEL SINGLE BOWL KITCHEN SINK (860X500X200X1.0MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    _product(db, "SORENTOBAG", "SORENTO PAPER BAG", category=db.info["junk_cat"])
    _product(db, "SORENTO188", "NOT USE THIS CODE", category=db.info["junk_cat"])
    return db


@pytest.fixture()
def turn_b_seed(db):
    """The live 12303548 catalogue shape: two double-bowl sinks differing only by
    thickness, so ranking the STATED value is the whole test."""
    _product(
        db,
        "ZZTKS12",
        "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    _product(
        db,
        "ZZTKS10",
        "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.0MM)",
        category=db.info["sink_cat"],
        brand_id=db.info["sorento"],
    )
    return db


def test_turn_12303509_returns_junk_free_display_populated_rows(client, turn_a_seed):
    body = client.post(
        RESOLVE,
        json={
            "query": "sorento double bowl kitchen sink",
            "tokens": ["Sorento", "double bowl kitchen sink"],
            "match_mode": "or",
            "spec_fallback": True,
        },
    ).json()

    matches = _all_spec_matches(body)
    assert matches, "the described sink must reach the ranker"

    codes = _codes_in_resolutions(body)
    assert "SORENTOBAG" not in codes
    assert "SORENTO188" not in codes

    for match in matches:
        display = match["display"]
        # Every spec-tier match carries a populated specifications block - a
        # renderer must be able to say WHY every row shown was offered, not
        # just the top one.
        assert display["specifications"], display
        # The two honesty channels never overlap: a key the customer earned is
        # never ALSO claimed as a house preference on the same row.
        assert not (
            set(display["matched_specs"]) & set(display["preferred_specs"])
        ), display

    assert "spec_asked" in body


def test_turn_12303548_ranks_the_stated_thickness_with_clean_honesty_fields(
    client, turn_b_seed
):
    body = client.post(
        RESOLVE,
        json={
            "query": "double bowl kitchen sink with thickness 1.0mm",
            "spec_fallback": True,
        },
    ).json()

    codes = [c["product_code"] for c in body.get("spec_candidates", [])]
    assert codes and codes[0] == "ZZTKS10", codes

    assert body.get("spec_unmet") == []
    assert body.get("unrecognized_terms") == []
