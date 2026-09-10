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


def test_predicate_block_carries_schemes_on_file_on_a_scheme_miss(client, db):
    """AC-1313 (S2): a scheme raw with no matching `certificate_scheme` option
    surfaces `predicate.schemes_on_file` on the wire, sorted; a resolvable scheme
    carries NO `schemes_on_file` key at all. Today `_leg_certificate` neither
    resolves the raw through a lookup set nor emits `schemes_on_file` anywhere in
    `resolve_product_set`'s return, so the miss call KeyErrors on the missing key
    before the resolvable call is even reached."""
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    def _certified(code, scheme):
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description="SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        cert = Certificate(
            id=str(uuid.uuid4()),
            scheme=scheme,
            certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(cert)
        db.flush()
        db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
        db.flush()
        return product

    _certified("ZZTCERT01", "PPS")
    _certified("ZZTCERT02", "SPAN")

    lookup_set = LookupSet(
        id=str(uuid.uuid4()), tenant_id=None, set_key="certificate_scheme",
        name="Certificate Scheme", is_active=True,
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(id=str(uuid.uuid4()), set_id=lookup_set.id, value="PPS", label="PPS", is_active=True)
    db.add(option)
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=option.id, keyword="pps scheme", locale=None))
    db.flush()

    miss = client.post(
        ENDPOINT,
        json={
            "query": "which kitchen sink has watermark cert",
            "free_terms": ["kitchen sink"],
            "require": {"certificate": {"scheme": "watermark"}},
        },
    )
    assert miss.status_code == 200
    miss_predicate = miss.json()["predicate"]
    assert miss_predicate["schemes_on_file"] == ["PPS", "SPAN"]
    assert "watermark" in miss_predicate["unrecognized_terms"]

    hit = client.post(
        ENDPOINT,
        json={
            "query": "which kitchen sink has pps cert",
            "free_terms": ["kitchen sink"],
            "require": {"certificate": {"scheme": "pps scheme"}},
        },
    )
    assert hit.status_code == 200
    assert "schemes_on_file" not in hit.json()["predicate"]


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


# --------------------------------------------------------------------------- #
# S3 follow-up (captain, after the S3 red-test report): AC-1306, guard the       #
# described set's class-word scoping when the caller sends NO product token at   #
# all (`tokens: []`) - the chatbot lane's own shape for "which tap has cert".     #
# --------------------------------------------------------------------------- #


def test_class_word_in_query_scopes_the_described_set(client, db):
    """AC-1306: with `tokens: []` (no product entity resolved, exactly the chatbot
    lane's own HAS-turn shape - see `tests/chatbot/test_lane_require.py`'s
    `test_set_answer_carries_the_header_and_shows_five` and siblings) the described set
    must still be scoped to the class word IN THE QUERY TEXT, not fall through to
    "nothing describes the set, count everything satisfying the require leg".

    World: one certified class-Tap product (ZZTTAP01) and one certified class-Wash-Basin
    product (ZZTBASIN01) - two DIFFERENT classes on purpose, so a test asserting "1
    qualifies" cannot pass by coincidence the way an all-Tap world would (the S3 tester's
    own finding, `test_lane_require.py`'s module-section banner comment).

    Contract for the coder: the resolver's HAS branch builds `free_terms` from (1) the
    raw of every product entity token that did NOT resolve, else (2) the remainder of
    `query` after removing `predicate_words` and the phrase stopwords, as ONE term; that
    term goes through `filter_specs` (measured directly: `filter_specs(db,
    free_terms=["tap"])` already resolves `class_labels=["Tap"]` today -
    `product_spec_search.py`'s own `resolve_classes_for_term`), so a class word scopes
    the set and an unknown phrase (`filter_specs(db, free_terms=["item"])` ->
    `unrecognized_terms=["item"]`) lands there instead.

    RED: today `app/api/v1/system/references.py`'s require branch reads
    `derive_search_inputs(db, query_text, specs=[], free_terms=[], ...)` and DISCARDS its
    own returned free terms (by design - merging the whole raw phrase back in would flag
    "which kitchen sinks have stock" itself as unrecognized, per that file's own comment),
    then calls `resolve_product_set(..., free_terms=payload.free_terms)` - and nothing on
    this request path ever populates `payload.free_terms` from `query`. So
    `filter_specs` never sees "tap" (or "item") as a free term either way, `specs=[]`
    stays empty (`derive_search_inputs`'s own deterministic pass does not bind a BARE
    class word to `specs` - only `filter_specs`'s `free_terms` argument resolves classes,
    per the measurement above), `described_given` is False, and BOTH the "which tap"
    and the "which item" call fall to the "nothing describes the set" branch, which
    counts every certified product with NO class restriction - so the FIRST assertion
    below (expects 1, tap-scoped) is what fails, against an actual `qualifying_total`
    of 2.
    """
    from app.models.certificate import Certificate, CertificateProduct

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    def _certified_product(code: str, description: str) -> Product:
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description=description,
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
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
        return product

    tap = _certified_product("ZZTTAP01", "ZZT CHROME TAP")
    _certified_product("ZZTBASIN01", "ZZT WHITE WASH BASIN")

    scoped = client.post(
        ENDPOINT,
        json={
            "query": "which tap has cert",
            "tokens": [],
            "require": {"certificate": True},
            "predicate_words": ["cert"],
        },
    )
    assert scoped.status_code == 200
    scoped_payload = scoped.json()
    assert scoped_payload["predicate"]["qualifying_total"] == 1, scoped_payload["predicate"]
    scoped_matches = [
        m
        for resolution in scoped_payload["resolutions"]
        for m in resolution["matches"]
        if m.get("match_tier") == "spec_search"
    ]
    assert [m["canonical_code"] for m in scoped_matches] == [tap.product_code]

    unscoped = client.post(
        ENDPOINT,
        json={
            "query": "which item has cert",
            "tokens": [],
            "require": {"certificate": True},
            "predicate_words": ["cert"],
        },
    )
    assert unscoped.status_code == 200
    assert unscoped.json()["predicate"]["qualifying_total"] == 2, unscoped.json()["predicate"]


# --------------------------------------------------------------------------- #
# Fix round (console findings, 11 Sep 2026, committed 3779b32d6) - AC-1305, C1:  #
# the gate is a WORD/CODE shape test, never a match TIER. Today's                #
# `_has_exact_product_match` (references.py ~line 1470) still gates on          #
# `match_tier in ("exact", "head_code")` alone, so a code-shaped PREFIX match    #
# (tier "prefix", never in that tuple) sails through and wrongly runs HAS, and   #
# a WORD that happens to hit an exact-tier product-code equality (a product     #
# literally coded "SORENTO") wrongly blocks it. Both are console-measured,      #
# not theoretical: "check stock srtwc286" (7 code variants, prefix tier) turned #
# into a set answer with a header, and "which sorento bidet has cert" stayed a  #
# picker because "sorento" resolved exact by CODE, not because it named a full  #
# product.                                                                       #
# --------------------------------------------------------------------------- #


def test_code_shaped_prefix_token_keeps_the_forward_path(client, db):
    """AC-1305: a CODE-SHAPED token (letters+digits mixed - "zztwc286") that
    resolves via PREFIX (not exact/head_code) to seven code variants must still
    block HAS - the response with `require` stays byte-identical to the same
    request without it. Contrast in the same test: a WORD token ("bidet",
    substring tier) with `require` still runs HAS - `predicate` present.

    RED: `_has_exact_product_match` only recognises tier in ("exact",
    "head_code"). "zztwc286" resolves at tier "prefix", which is not in that
    tuple, so the function returns False, `require` is NOT skipped, and the
    prefix case wrongly grows a `predicate` block today.
    """
    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    variants = [
        "ZZTWC286-SH", "ZZTWC286-SH-150", "ZZTWC286-SH-200", "ZZTWC286-BL",
        "ZZTWC286-BL-150", "ZZTWC286-WH", "ZZTWC286-WH-CR",
    ]
    for code in variants:
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description="SORENTO WATER CLOSET SUITE",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=Decimal("1.00"),
            )
        )
    db.flush()

    with_require = client.post(
        ENDPOINT,
        json={"query": "zztwc286", "tokens": ["zztwc286"], "require": {"stock": True}},
    )
    without_require = client.post(
        ENDPOINT,
        json={"query": "zztwc286", "tokens": ["zztwc286"]},
    )
    assert with_require.status_code == 200
    assert without_require.status_code == 200
    with_body = with_require.json()
    without_body = without_require.json()
    with_body.pop("elapsed_ms", None)
    without_body.pop("elapsed_ms", None)
    assert with_body == without_body
    assert "predicate" not in with_body

    # Contrast: a WORD token, substring tier, still runs HAS.
    _three_bidets(db)
    word_response = client.post(
        ENDPOINT,
        json={"query": "bidet", "tokens": ["bidet"], "require": {"certificate": True}},
    )
    assert word_response.status_code == 200
    assert "predicate" in word_response.json()


def test_word_token_with_an_exact_name_hit_does_not_block_has(client, db):
    """AC-1305: a WORD token that happens to resolve at the "exact" tier - a
    product literally coded "SORENTO" (case-insensitive equality is the only way
    a product probe assigns "exact") - must never block HAS: the shape test is
    the TOKEN's own, not the tier it happened to resolve at. `require` still
    runs, `predicate` present.

    RED: `_has_exact_product_match` returns True for ANY product match at tier
    "exact", whatever shape the token is - "sorento" blocks `require` today,
    same as a real code would, so `predicate` is wrongly absent.
    """
    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    db.add(
        Product(
            id=str(uuid.uuid4()),
            product_code="SORENTO",
            product_name="SORENTO",
            description="SORENTO BRAND PLACEHOLDER ROW",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
    )
    db.flush()
    _three_bidets(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "sorento bidet",
            "tokens": ["sorento", "bidet"],
            "require": {"certificate": True},
        },
    )
    assert response.status_code == 200
    assert "predicate" in response.json(), response.json()


# --------------------------------------------------------------------------- #
# Fix round - AC-1306, C2: the scope term comes from the ENTITY the head        #
# retyped (a category noun -> an unresolved product token), never from taking   #
# every leftover content word in the raw sentence as one joined phrase. Both    #
# cases below currently reproduce green under direct construction (see the      #
# tester's own report) - kept in the suite as the AC-1306 regression guard the  #
# captain named, not withdrawn, but flagged HONESTLY per each docstring rather   #
# than forced red: this file's job is the acceptance criterion, and a defect     #
# that does not reproduce under the given inputs is itself a finding to hand     #
# back, not a reason to invent different inputs until something breaks.          #
# --------------------------------------------------------------------------- #


def test_scope_term_comes_from_the_entity_not_the_sentence(client, db):
    """AC-1306/C2: a certified class-Tap product and a certified class-Wash-Basin
    product; "which tap has cert" with `tokens: ["tap"]` (the head's retype of a
    category entity into an unresolved product token) and `predicate_words`
    covering every cert-word variant must scope to ONLY the tap
    (`qualifying_total == 1`), never report the compound "tap cert" (or "tap
    certificate") in `unrecognized_terms`. Second case: the same world, `tokens:
    []` (no product token sent at all - the plain chatbot-lane shape), query
    "which tap has certificate" instead - same result.

    NOT RED as constructed - measured directly against this exact world and
    these exact parameters (`git show`-able probe, dropped after confirming):
    both cases already return `qualifying_total == 1` and
    `unrecognized_terms == []` today. `_has_turn_free_terms`
    (`app/api/v1/system/references.py`) already strips `predicate_words` from
    `query_text` before calling `_content_words`, and `_PHRASE_STOPWORDS`
    already carries "which" and "has" (A2), so neither case's remainder ever
    contains more than the bare class word "tap". Reported to the captain as a
    finding rather than forced: the console defect this AC names may already be
    fixed by the C2 repair commit (`b7833f48c`, which landed before the console
    findings were measured), or it needs an input shape this construction does
    not reach. Kept as the regression guard AC-1306 asks for.
    """
    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    def _certified_tail_class(code: str, description: str) -> Product:
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description=description,
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        from app.models.certificate import Certificate, CertificateProduct

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
        return product

    tap = _certified_tail_class("ZZTSCOPE1", "ZZT CHROME TAP")
    _certified_tail_class("ZZTSCOPE2", "ZZT WHITE WASH BASIN")

    case1 = client.post(
        ENDPOINT,
        json={
            "query": "which tap has cert",
            "tokens": ["tap"],
            "require": {"certificate": True},
            "predicate_words": ["cert", "certificate", "Certification"],
        },
    )
    assert case1.status_code == 200
    predicate1 = case1.json()["predicate"]
    assert predicate1["qualifying_total"] == 1, predicate1
    assert predicate1["unrecognized_terms"] == [], predicate1
    assert "tap cert" not in predicate1["unrecognized_terms"]
    assert "tap certificate" not in predicate1["unrecognized_terms"]

    case2 = client.post(
        ENDPOINT,
        json={
            "query": "which tap has certificate",
            "tokens": [],
            "require": {"certificate": True},
            "predicate_words": ["certificate", "Certification"],
        },
    )
    assert case2.status_code == 200
    predicate2 = case2.json()["predicate"]
    assert predicate2["qualifying_total"] == 1, predicate2
    assert predicate2["unrecognized_terms"] == [], predicate2
    assert "tap cert" not in predicate2["unrecognized_terms"]
    assert "tap certificate" not in predicate2["unrecognized_terms"]
