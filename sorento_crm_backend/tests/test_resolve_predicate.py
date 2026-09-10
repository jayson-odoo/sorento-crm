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

    Cases 1 and 2 are NOT RED as constructed - measured directly against this
    exact world and these exact parameters (`git show`-able probe, dropped
    after confirming): both already return `qualifying_total == 1` and
    `unrecognized_terms == []` today. `_has_turn_free_terms`
    (`app/api/v1/system/references.py`) already strips `predicate_words` from
    `query_text` before calling `_content_words`, and `_PHRASE_STOPWORDS`
    already carries "which" and "has" (A2), so neither case's remainder ever
    contains more than the bare class word "tap". Reported to the captain as a
    finding rather than forced: the console defect this AC names may already be
    fixed by the C2 repair commit (`b7833f48c`, which landed before the console
    findings were measured), or it needs an input shape this construction does
    not reach. Kept as the regression guard AC-1306 asks for.

    Case 3 (captain follow-up, 11 Sep 2026) is the input shape that DOES
    reproduce it: the live console turn's parser normalised the attachment_type
    entity's raw to "certificate" (canonical "Certification") while the
    customer actually typed "cert" - so `predicate_words` never contains the
    literal word the sentence carries, and stripping only whole-word entries
    from that list leaves "cert" in the remainder. `query`: "which tap has
    cert"; `tokens: []`; `predicate_words: ["certificate", "Certification",
    "check_product_attachment"]` - deliberately no literal "cert" anywhere in
    that list. Per the PLAN's own C2 contract, every word matching `_CERT_RE`
    (`app/services/chatbot/head/output_exchange.py`) must ALSO be stripped
    from the remainder, on top of `predicate_words` - "cert" itself matches
    `_CERT_RE` (`r"cert|ikram|span|sirim|bomba|ms\s?[0-9]|halal"`).

    RED: `_has_turn_free_terms` strips only `payload.predicate_words`'
    whole-word matches, never runs `_CERT_RE` over the remainder at all, so
    "cert" survives into `_content_words("which tap has cert")` alongside
    "tap", and the scope term becomes the joined "tap cert" - measured
    directly: `filter_specs` cannot bind that compound to any class, so it
    reports the whole term unrecognized (`unrecognized_terms == ["tap
    cert"]`) and `qualifying_total` is 0 (the honest-zero path, AC-1301/1302 -
    a described-but-unrecognised set qualifies nothing), never the 1 this
    case demands.
    """
    # Case 3's unstripped "tap cert" remainder reaches a last-resort trigram
    # probe across every entity type, including transporters, whose
    # `similarity()` needs `pg_trgm` - installed in `public`, which
    # `blank_session()`'s own `search_path` deliberately excludes so raw SQL
    # cannot leak onto the real tables. Widening it here is scoped to this
    # test's `SET LOCAL` only.
    from sqlalchemy import text as sa_text

    current_search_path = db.execute(sa_text("SHOW search_path")).scalar()
    db.execute(sa_text(f"SET LOCAL search_path TO {current_search_path}, public"))

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

    case3 = client.post(
        ENDPOINT,
        json={
            "query": "which tap has cert",
            "tokens": [],
            "require": {"certificate": True},
            "predicate_words": ["certificate", "Certification", "check_product_attachment"],
        },
    )
    assert case3.status_code == 200
    predicate3 = case3.json()["predicate"]
    assert predicate3["qualifying_total"] == 1, predicate3
    assert predicate3["unrecognized_terms"] == [], predicate3
    assert "tap cert" not in predicate3["unrecognized_terms"]
    assert "tap certificate" not in predicate3["unrecognized_terms"]


# --------------------------------------------------------------------------- #
# Console fix round 2 (11 Sep 2026, PLAN-attribute-first-asks.md R1/R2/R5/R7,   #
# AC-1305/AC-1327/AC-1328/AC-1330). The lane's own request ALWAYS carries       #
# `match_mode: "and"` (see the uncommitted `scripts/chatbot_replay_resolve.py`  #
# the captain measured this round with), so the forward result for the lane's  #
# real shape lives in `intersection` (or, once the AND probe fails outright     #
# and `fallback_to_all_types` degrades to OR-mode-under-whitelist, back in      #
# `resolutions`) - never the bare OR-mode `resolutions` shape every test above  #
# this banner posts.                                                            #
# --------------------------------------------------------------------------- #


def test_code_shaped_prefix_in_and_mode_keeps_the_forward_path(client, db):
    """AC-1305/R1 (fix round 2): the lane ALWAYS sends `match_mode: "and"`. AND
    mode's own product probe (`_and_probe_product`) stamps EVERY row it returns
    `match_tier="and"` - it never produces `"exact"` or `"head_code"` - so a
    code-shaped PREFIX match (seven products sharing the "ZZTWC286" prefix) can
    NEVER satisfy `_has_exact_product_match`'s AND-mode branch, which still gates
    on `match_tier in ("exact", "head_code")` alone. Under the lane's real
    request shape the code-shape gate silently never fires, and a caller who
    typed a complete code gets `require` run over it anyway.

    RED: `with_require` and `without_require` diverge (`with_require` grows a
    `predicate` block) instead of being byte-identical.
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
        json={
            "query": "zztwc286",
            "tokens": ["zztwc286"],
            "match_mode": "and",
            "require": {"stock": True},
        },
    )
    without_require = client.post(
        ENDPOINT,
        json={"query": "zztwc286", "tokens": ["zztwc286"], "match_mode": "and"},
    )
    assert with_require.status_code == 200
    assert without_require.status_code == 200
    with_body = with_require.json()
    without_body = without_require.json()
    with_body.pop("elapsed_ms", None)
    without_body.pop("elapsed_ms", None)
    assert with_body == without_body
    assert "predicate" not in with_body


def test_has_removes_word_token_product_matches_from_the_forward_result(client, db):
    """AC-1327/R2 (fix round 2): once HAS ran, a WORD token's own forward product
    matches (a plain substring hit on the product CODE, unrelated to the
    described set) must not survive alongside the spec_search resolution - only
    the spec_search resolution may carry product matches. A non-product
    resolution (the attachment_type hit for "certificate") is untouched.

    World: two products whose CODE contains "TAP" as a plain substring
    ("ZZT-COLD-TAP", "ZZT-HOT-TAP", neither certified - a forward hit for the
    WORD token "tap", tier "substring", nothing to do with the certificate leg),
    plus three certified class-Tap products whose codes do NOT contain "tap" at
    all, so they can only qualify through the class binding / spec search.

    Posted with `match_mode: "and"` and `allowed_entity_types` covering the
    lane's own hint shape (`category` for "tap", `attachment_type` for
    "certificate") plus `fallback_to_all_types: True` - the lane's real body
    shape, and also the ONLY way "tap" (which no product CODE starts with)
    reaches the forward substring probe at all: the AND-mode cross-token
    intersection is empty (product resolution is code-only, and no code
    contains both "tap" and "certificate"), so the resolver degrades to
    OR-mode-under-whitelist and per-token fallback - exactly the path a live
    "which tap has cert" turn takes.

    RED: nothing on this path strips a WORD token's own forward product matches
    once HAS has run - `_emit_spec_matches` only APPENDS the spec_search
    resolution - so the "tap" resolution's two forward substring matches sit
    right beside the 3-match spec_search resolution.
    """
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.resources import AttachmentType

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    at = AttachmentType(
        id=str(uuid.uuid4()), code="CERTIFICATE", type_name="Certificate", allowed_extensions="pdf"
    )
    db.add(at)
    db.flush()

    def _plain(code, name):
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=name,
            description=f"{name} DESCRIPTION",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        return product

    _plain("ZZT-COLD-TAP", "ZZT COLD TAP")
    _plain("ZZT-HOT-TAP", "ZZT HOT TAP")

    def _certified_tap(code):
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description="ZZT CHROME BASIN TAP",
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

    certified_codes = sorted(_certified_tap(f"ZZTCERT0{i}").product_code for i in range(3))

    response = client.post(
        ENDPOINT,
        json={
            "query": "which tap has certificate",
            "tokens": ["tap", "certificate"],
            "allowed_entity_types": ["category", "attachment_type"],
            "match_mode": "and",
            "domain": "product_attachment",
            "fallback_to_all_types": True,
            "require": {"certificate": True},
            "predicate_words": ["cert"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["predicate"]["qualifying_total"] == 3, payload["predicate"]

    product_codes_by_token: dict[str, list[str]] = {}
    for resolution in payload.get("resolutions") or []:
        codes = [
            m["canonical_code"]
            for m in resolution.get("matches") or []
            if m.get("entity_type") == "product"
        ]
        if codes:
            product_codes_by_token[resolution.get("token")] = codes

    # Only the spec_search resolution (keyed on the whole query text) may carry
    # product matches once HAS has run.
    assert set(product_codes_by_token) <= {"which tap has certificate"}, product_codes_by_token
    assert sorted(product_codes_by_token.get("which tap has certificate", [])) == certified_codes

    attachment_resolution = next(
        (r for r in payload.get("resolutions") or [] if r.get("token") == "certificate"), None
    )
    assert attachment_resolution is not None, payload.get("resolutions")
    assert any(
        m.get("entity_type") == "attachment_type" for m in attachment_resolution.get("matches") or []
    )

    for m in payload.get("intersection") or []:
        assert m.get("entity_type") != "product" or m.get("match_tier") == "spec_search"


def test_word_token_resolving_to_non_products_still_scopes_the_set(client, db):
    """AC-1330/R7 (fix round 2): a WORD token's raw ALWAYS defines the described
    set's scope, whatever entity type it happened to resolve to - "sink"
    resolving to a CUSTOMER (never a product) must still scope the incoming-leg
    count to class Kitchen Sink, not fall through to "nothing describes the set,
    count every open-incoming product regardless of class".

    World: a customer whose code starts with "SINK" (`_prefix_probe_customer`'s
    own tier), a class-Kitchen-Sink product with an open incoming line, and a
    class-Tap product ALSO with an open incoming line - two DIFFERENT classes,
    both qualifying the `incoming` leg, so "count everything" (2) and "count
    only the Kitchen Sink" (1) are not the same number. Neither product's CODE
    contains "sink" as a substring (unlike its class-naming description) - AND
    mode's own product probe is CODE-ONLY, so a code that happened to contain
    "sink" would short-circuit the very fallback-to-customer path this AC is
    about, and "sink" would never reach the customer probe at all.

    RED: `_has_turn_free_terms` treats "sink" as an ALREADY-RESOLVED product
    token the moment ANY resolution (of ANY entity_type) carries a match for it
    - the customer hit alone satisfies that check - so it returns `[]` free
    terms, the described set is left unscoped, and `resolve_product_set` counts
    BOTH products (`qualifying_total == 2`), never the 1 this AC demands.
    """
    from datetime import date

    from app.models.order import Customer
    from app.models.procurement import InboundShipment, InboundShipmentLine

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    customer = Customer(id=str(uuid.uuid4()), customer_code="SINK-TR", customer_name="ZZT SINK TRADING")
    db.add(customer)
    db.flush()

    def _open_incoming_product(code, description):
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
        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"ZZT-{uuid.uuid4().hex[:8]}",
            shipment_date=date.today(),
            actual_arrival_date=None,
        )
        db.add(shipment)
        db.flush()
        db.add(
            InboundShipmentLine(
                id=str(uuid.uuid4()),
                shipment_id=shipment.id,
                product_id=product.id,
                quantity_shipped=10,
                quantity_received=0,
            )
        )
        db.flush()
        return product

    _open_incoming_product("ZZT-9001", "SORENTO S/STEEL KITCHEN SINK")
    _open_incoming_product("ZZT-9002", "ZZT CHROME BASIN TAP")

    response = client.post(
        ENDPOINT,
        json={
            "query": "which sink has incoming",
            "tokens": ["sink"],
            "allowed_entity_types": ["product"],
            "match_mode": "and",
            "fallback_to_all_types": True,
            "require": {"incoming": True},
            "predicate_words": ["incoming"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    predicate = payload["predicate"]
    assert predicate["qualifying_total"] == 1, predicate
    assert predicate.get("class_labels") == ["Kitchen Sink"], predicate


def test_scheme_word_matches_the_register_spelling_without_a_lookup_option(client, db):
    """AC-1328/R5 (fix round 2): `_leg_certificate` must match a scheme word
    against the register's OWN active scheme spellings by case-insensitive
    equality BEFORE consulting the (possibly empty/absent) `certificate_scheme`
    lookup set - "pps" against a register carrying "PPS" and "SPAN", with NO
    lookup set at all, must count only the PPS product and report nothing
    unrecognized.

    RED: `_leg_certificate` only calls `_lookup_resolve(db, "certificate_scheme",
    scheme)` - with no matching option/keyword it returns None and the leg
    raises `_UnrecognizedLabel("pps", ...)`, so `qualifying_total` is 0 and "pps"
    lands in `unrecognized_terms` instead of the 1 this case demands.
    """
    from app.models.certificate import Certificate, CertificateProduct

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

    _certified("ZZTSCH01", "PPS")
    _certified("ZZTSCH02", "SPAN")

    response = client.post(
        ENDPOINT,
        json={
            "query": "which kitchen sink has pps cert",
            "free_terms": ["kitchen sink"],
            "require": {"certificate": {"scheme": "pps"}},
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["qualifying_total"] == 1, predicate
    assert predicate["unrecognized_terms"] == [], predicate
    assert "schemes_on_file" not in predicate, predicate


# --------------------------------------------------------------------------- #
# Third console pass (11 Sep 2026, PLAN-attribute-first-asks.md R13,           #
# AC-1332) - the LLM parser variant that put `understand_phrase: true` on the  #
# wire tripped a MODEL read the HAS branch was never meant to run: the         #
# deterministic replay of the same stored parser output (no model key at all) #
# answered cleanly, while the live turn's model-derived free term "item pps"  #
# poisoned the described set.                                                 #
# --------------------------------------------------------------------------- #


def _pps_certified_world(db):
    """One PPS-scheme certified product, unrelated to class scoping - just
    enough register data for the `certificate.scheme` leg to resolve "PPS"
    without also tripping AC-1328/R5's own scheme-miss path."""
    from app.models.certificate import Certificate, CertificateProduct

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    product = Product(
        id=str(uuid.uuid4()),
        product_code="ZZTPPS01",
        product_name="ZZTPPS01",
        description="ZZT SOME PRODUCT",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    cert = Certificate(
        id=str(uuid.uuid4()), scheme="PPS", certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}", status="active"
    )
    db.add(cert)
    db.flush()
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
    db.flush()
    return product


def test_has_branch_never_calls_the_model_phrase_reader(client, db, monkeypatch):
    """AC-1332/R13 (third console pass): the HAS branch (`require` present) must
    derive its class/product_type/brand bindings deterministically ONLY - the
    MODEL phrase reader stays on the spec_fallback path where it was built for
    (it costs 2-3 seconds and is gated there by design), never invoked here even
    when the caller's own `understand_phrase` is true, which is the lane's real
    value on every turn. Measured live: "which item has PPS cert" answered "I
    don't know 'item pps' as a product type" - "item pps" is a MODEL-derived free
    term, never produced by the deterministic word-level reader, and never seen
    in the replay of the exact same stored parser output run without the model.

    RED: `app/api/v1/system/references.py`'s require branch calls
    `derive_search_inputs(..., allow_model=payload.understand_phrase)` - a
    caller that sends the lane's own real `understand_phrase: true` lets the
    model run, tripping this test's monkeypatched guard with an AssertionError
    (caught nowhere on this path, so it surfaces as a 500, not a clean miss).
    """
    import app.services.product_spec_understanding as psu

    real_derive_search_inputs = psu.derive_search_inputs

    def _guarded(db_arg, *args, **kwargs):
        if kwargs.get("allow_model"):
            raise AssertionError(
                "derive_search_inputs called with allow_model=True on a HAS (require-present) turn"
            )
        return real_derive_search_inputs(db_arg, *args, **kwargs)

    monkeypatch.setattr(psu, "derive_search_inputs", _guarded)
    # references.py's require branch does `from app.services.product_spec_understanding
    # import derive_search_inputs` INSIDE the function body, so this patch of the
    # module attribute is read fresh on every call - no second patch target needed.

    _pps_certified_world(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "which item has PPS cert",
            "tokens": [],
            "match_mode": "and",
            "understand_phrase": True,
            "require": {"certificate": {"scheme": "PPS"}},
            "predicate_words": ["PPS cert"],
        },
    )
    assert response.status_code == 200
    assert response.json()["predicate"]["unrecognized_terms"] == []


def test_predicate_words_are_stripped_word_by_word(client, db):
    """AC-1332 (third console pass): a phrase-shaped `predicate_words` entry
    ("PPS cert", the parser's single attachment_type raw) must strip cleanly out
    of the described-set remainder, word by word - not survive as a leftover
    unrecognised phrase. The query names no class, so the scoped set is
    unrestricted (no `class_labels`) and nothing is reported unrecognized.

    Likely green today, kept as the regression guard AC-1332 asks for: the
    query's predicate word IS one contiguous phrase in the sentence
    ("...has PPS cert"), so `_strip_predicate_words`'s own whole-phrase regex
    already matches it without needing a word-by-word split.
    """
    _pps_certified_world(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "which item has PPS cert",
            "tokens": [],
            "match_mode": "and",
            "understand_phrase": False,
            "require": {"certificate": {"scheme": "PPS"}},
            "predicate_words": ["PPS cert"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["unrecognized_terms"] == [], predicate
    assert not predicate.get("class_labels"), predicate


# --------------------------------------------------------------------------- #
# Security review (11 Sep 2026, PLAN-attribute-first-asks.md SEC-S1, AC-1334) #
# --------------------------------------------------------------------------- #


def test_resolver_threads_access_levels_into_the_promotion_leg(client, db):
    """AC-1334/SEC-S1: the resolve endpoint must thread its own `access_levels`
    field into the promotion leg, not only into the ordinary entity-resolution
    filter `_apply_promotion_access_levels_filter` already covers - a HAS turn
    ("which tap has promo") must count only the promotions the caller's tier
    can see.

    World: two class-Tap products (mirrors the `test_product_predicate_
    service.py` world), one promotion open to access code X, the other
    restricted to code Y; POST with `access_levels: ["<name for X>"]`.

    RED: the require branch never reads `payload.access_levels` at all when
    calling `resolve_product_set` (measured: `references.py`'s require branch
    has no `access_levels=` keyword in that call) - `qualifying_total` counts
    BOTH promotions regardless of the caller's tier, so this is 2, not the 1
    this AC demands.
    """
    from app.models.access import ContactAccessType
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()

    db.add(ContactAccessType(code="zzt_code_x", name="ZZT Level X"))
    db.add(ContactAccessType(code="zzt_code_y", name="ZZT Level Y"))
    db.flush()

    def _promo_tap(code, access_levels):
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description="ZZT CHROME BASIN TAP",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        promo = Promotion(
            id=str(uuid.uuid4()), description=f"ZZT promo {code}", is_active=True, access_levels=access_levels
        )
        db.add(promo)
        db.flush()
        group = PromotionGroup(id=uuid.uuid4(), promotion_id=promo.id, group_name="G")
        db.add(group)
        db.flush()
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()), promotion_id=promo.id, promotion_group_id=group.id, product_id=product.id
            )
        )
        db.flush()

    _promo_tap("ZZTPROMOX", ["zzt_code_x"])
    _promo_tap("ZZTPROMOY", ["zzt_code_y"])

    response = client.post(
        ENDPOINT,
        json={
            "query": "which tap has promo",
            "tokens": [],
            "match_mode": "and",
            "access_levels": ["ZZT Level X"],
            "require": {"promotion": True},
            "predicate_words": ["promo"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["qualifying_total"] == 1, predicate


def test_predicate_words_strip_word_by_word_when_not_contiguous(client, db):
    """AC-1332/REV-S4: `predicate_words` must strip WORD BY WORD, not only as
    one contiguous phrase - "which item has PPS certificate" (the parser
    normalised "cert" to "certificate", so the literal phrase "PPS cert" is no
    longer contiguous in the sentence) must still leave nothing unrecognized.

    RED: `_strip_predicate_words`'s regex matches the whole phrase "PPS cert"
    as one unit with a trailing word-boundary assertion - "PPS cert" is not
    followed by a word boundary inside "PPS certificate" (the "i" of
    "certificate" continues the word), so the match fails entirely and both
    "PPS" and "certificate" survive into the remainder. "certificate" itself
    gets dropped later by `_CERT_WORD_RE`, but "PPS" does not, and the
    described-set reader reports the leftover compound "item pps" as an
    unrecognized term - the reviewer's own measurement.
    """
    _pps_certified_world(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "which item has PPS certificate",
            "tokens": [],
            "match_mode": "and",
            "understand_phrase": False,
            "require": {"certificate": {"scheme": "PPS"}},
            "predicate_words": ["PPS cert"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["unrecognized_terms"] == [], predicate


# --------------------------------------------------------------------------- #
# Fix round 3 (11 Sep 2026, PLAN-attribute-first-asks.md R14, AC-1338) - a     #
# bare `{"certificate": true}` require whose remainder holds a word equal      #
# (case-insensitive) to a register scheme spelling or a `certificate_scheme`   #
# lookup keyword must be promoted to `{"certificate": {"scheme": ...}}`.       #
# --------------------------------------------------------------------------- #


def test_bare_certificate_true_recovers_a_register_scheme_from_the_remainder(client, db):
    """AC-1338/R14(a): "which item has PPS cert" with a BARE `{"certificate":
    true}` require (the lane's real shape today - the scheme was never split
    off the attachment_type raw) must recover "PPS" from the remainder against
    the register's own active scheme spelling, promote `require` to
    `{"certificate": {"scheme": "PPS"}}`, and never report "pps" unrecognized.

    RED: the resolver's HAS branch never attempts scheme recovery for a bare
    `true` - `require` stays exactly `{"certificate": true}` and "pps" reaches
    `filter_specs` as an ordinary described-set word, which the vocabulary does
    not recognize.
    """
    _pps_certified_world(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "which item has PPS cert",
            "tokens": [],
            "match_mode": "and",
            "require": {"certificate": True},
            "predicate_words": ["certificate"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["require"] == {"certificate": {"scheme": "PPS"}}, predicate
    assert "pps" not in [str(t).lower() for t in predicate["unrecognized_terms"]], predicate
    assert predicate["qualifying_total"] >= 1, predicate


def test_bare_certificate_true_recovers_a_scheme_through_the_lookup_keyword(client, db):
    """AC-1338/R14(b): the same recovery through a `certificate_scheme` lookup
    KEYWORD, not just the register's own spelling - "watermark" mapped to
    scheme "WCM" via a seeded lookup option/keyword, register carrying only
    "WCM" itself (no "watermark" spelling to match by equality).

    RED: no scheme recovery runs at all for a bare `true`, so "watermark"
    reaches `filter_specs` as an unrecognized set word and `require` stays
    `{"certificate": true}`.
    """
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet

    cat = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    product = Product(
        id=str(uuid.uuid4()),
        product_code="ZZTWCM01",
        product_name="ZZTWCM01",
        description="ZZT SOME PRODUCT",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    cert = Certificate(
        id=str(uuid.uuid4()), scheme="WCM", certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}", status="active"
    )
    db.add(cert)
    db.flush()
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
    db.flush()

    lookup_set = LookupSet(
        id=str(uuid.uuid4()), tenant_id=None, set_key="certificate_scheme",
        name="Certificate Scheme", is_active=True,
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(id=str(uuid.uuid4()), set_id=lookup_set.id, value="WCM", label="WCM", is_active=True)
    db.add(option)
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=option.id, keyword="watermark"))
    db.flush()

    response = client.post(
        ENDPOINT,
        json={
            "query": "which item has watermark cert",
            "tokens": [],
            "match_mode": "and",
            "require": {"certificate": True},
            "predicate_words": ["certificate"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["require"] == {"certificate": {"scheme": "WCM"}}, predicate
    assert "watermark" not in [str(t).lower() for t in predicate["unrecognized_terms"]], predicate


def test_bare_certificate_true_stays_bare_when_remainder_names_no_scheme(client, db):
    """AC-1338/R14(c) regression: "which zzqx has cert" names no scheme word at
    all ("zzqx" is neither a register spelling nor a lookup keyword) - `require`
    must stay bare `{"certificate": true}` and "zzqx" must still be reported
    unrecognized, exactly as it is today. Guards the fix against treating every
    remainder word as a candidate scheme.

    Likely GREEN today (no scheme recovery runs at all yet, so `require` is
    already bare and "zzqx" already unrecognized) - kept as the regression
    guard R14(c) names explicitly, reported honestly rather than forced red.
    """
    _pps_certified_world(db)

    response = client.post(
        ENDPOINT,
        json={
            "query": "which zzqx has cert",
            "tokens": ["zzqx"],
            "match_mode": "and",
            "require": {"certificate": True},
            "predicate_words": ["certificate"],
        },
    )
    assert response.status_code == 200
    predicate = response.json()["predicate"]
    assert predicate["require"] == {"certificate": True}, predicate
    assert "zzqx" in [str(t).lower() for t in predicate["unrecognized_terms"]], predicate
