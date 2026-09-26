"""AC-S1-1..S1-5: price tag AI extract product matching goes through the
shared entity resolver instead of `_canonical_product_code`'s private ILIKE.

See documentation/plans/dealer-kit/PLAN-price-tag-ai-extract-resolver.md (D1, D2)
and price-tag-ai-extract-resolver-acceptance-criteria.md (S1).

Drives `AIExtractService._extract_products(parsed)` directly, the same seam
`test_ai_extract_service.py::test_extract_products_*` already exercises, but
with a real Postgres session (`tests/_pg_fixture.py::blank_session`) so exact
matches, company scope and the resolver spy are all real.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet
from app.services.ai_extract.extract_service import AIExtractService
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"
MOCHA = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _mocha(db) -> str:
    if db.query(Company).filter(Company.id == MOCHA).first() is None:
        db.add(
            Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True)
        )
        db.flush()
    return MOCHA


def _product(db, code: str, *, company_id: str = SORENTO, is_active: bool = True) -> Product:
    cat = ProductCategory(
        id=_uid(), category_code=unique_code("cat")[:50], category_name="ZZT cat"
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom")[:20], uom_name="Each")
    db.add_all([cat, uom])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=code,
        product_name=f"ZZT {code}",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=1,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _product_set(db, set_code: str, *, company_id: str = SORENTO) -> ProductSet:
    row = ProductSet(
        id=_uid(), company_id=company_id, set_code=set_code, name=f"ZZT {set_code}",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _parsed(*codes: str) -> dict:
    return {
        "products": [
            {"product_code": c, "product_name": "raw name", "quantity": 1} for c in codes
        ]
    }


# --------------------------------------------------------------------------- #
# AC-S1-1: separator / case variants resolve to the stored, canonical code.
# --------------------------------------------------------------------------- #
SEPARATOR_CASES = [
    pytest.param("Srt6536 DIY", "SRT6536-DIY", id="space-mixed-case"),
    pytest.param("srt6536-diy", "SRT6536-DIY", id="dash-lower-case"),
    pytest.param("SRT6536DIY", "SRT6536-DIY", id="stripped-upper-case"),
    pytest.param("srt384-6 diy", "SRT384-6-DIY", id="mixed-dash-space"),
    pytest.param("SRTKT74SS BL", "SRTKT74SS-BL", id="space-upper-case"),
]


# --------------------------------------------------------------------------- #
# S1 (code review): a resolved match reports the CRM's own product_name, not
# the sales order's freeform description the LLM read off the page - the two
# drift, and what the salesperson applies onto the line is what marketing and
# the salesperson read back.
# --------------------------------------------------------------------------- #
def test_resolved_match_reports_the_crm_name_not_the_llm_description(db):
    product = _product(db, "SRTNAME001")  # product_name = "ZZT SRTNAME001"
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("SRTNAME001"))
    assert len(out) == 1
    assert out[0].product_name == product.product_name
    assert out[0].product_name != "raw name"


def test_a_miss_keeps_the_llm_description(db):
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("ZZT-NOTHING-LIKE-IT"))
    assert len(out) == 1
    assert out[0].product_name == "raw name"


@pytest.mark.parametrize("raw, stored", SEPARATOR_CASES)
def test_extracted_code_normalizes_through_resolver(db, raw, stored):
    product = _product(db, stored)
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed(raw))
    assert len(out) == 1
    assert out[0].product_code == stored
    assert out[0].match == "product"
    assert out[0].product_id == product.id


# --------------------------------------------------------------------------- #
# AC-S1-2: no exact match keeps the raw text, no match, no ids.
# --------------------------------------------------------------------------- #
def test_no_exact_match_keeps_raw_text_and_reports_no_match(db):
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("ZZT-NOTHING-LIKE-IT"))
    assert len(out) == 1
    assert out[0].product_code == "ZZT-NOTHING-LIKE-IT"
    assert out[0].match is None
    assert out[0].product_id is None
    assert out[0].product_set_id is None


# --------------------------------------------------------------------------- #
# S2 (code review): a token with TWO scoped hits (a normalized collision - two
# codes that flatten to the same dash/whitespace-stripped form) is a real
# ambiguity, not a match to guess between - the raw text is kept, same as no
# match at all. Tier 1 exact only flags a multi-hit token `ambiguous` for
# `certificate` (see entity_resolver.py); `_resolve_product_codes` has its own
# `len(tr.matches) != 1` guard so a product/product_set collision is caught
# regardless.
# --------------------------------------------------------------------------- #
def test_two_scoped_hits_for_one_token_keeps_raw_text_and_no_match(db):
    base = unique_code("SRTAMB")
    code_a = f"{base}-1"
    code_b = f"{base}1"
    _product(db, code_a)
    _product(db, code_b)

    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed(code_a))

    assert len(out) == 1
    assert out[0].product_code == code_a
    assert out[0].match is None
    assert out[0].product_id is None
    assert out[0].product_set_id is None


# --------------------------------------------------------------------------- #
# AC-S1-3: a ProductSet.set_code match reports match="product_set".
# --------------------------------------------------------------------------- #
def test_set_code_match_reports_product_set(db):
    pset = _product_set(db, "SRTWC8608-RL")
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("srtwc8608 rl"))
    assert len(out) == 1
    assert out[0].match == "product_set"
    assert out[0].product_set_id == pset.id
    assert out[0].product_id is None
    assert out[0].product_code == "SRTWC8608-RL"


# --------------------------------------------------------------------------- #
# AC-S1-4: a product belonging to another company is not matched.
# --------------------------------------------------------------------------- #
def test_product_of_another_company_is_not_matched(db):
    mocha = _mocha(db)
    _product(db, "SRT-MOCHA-ONLY", company_id=mocha)
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("SRT-MOCHA-ONLY"))
    assert len(out) == 1
    assert out[0].match is None
    assert out[0].product_id is None
    assert out[0].product_code == "SRT-MOCHA-ONLY"


# --------------------------------------------------------------------------- #
# AC-S1-5: `_canonical_product_code` is gone; `_extract_products` calls
# `resolve_references` exactly once for the whole code list, exact-tier only.
# --------------------------------------------------------------------------- #
def test_canonical_product_code_helper_is_removed():
    assert not hasattr(AIExtractService, "_canonical_product_code")


def test_extract_products_calls_resolver_once_with_whole_code_list_exact_only(
    db, monkeypatch
):
    import app.services.ai_extract.extract_service as extract_service_mod
    from app.services.entity_resolver import ResolutionResult

    calls: list[tuple] = []

    def _fake_resolve_references(db_arg, codes, **kwargs):
        calls.append((db_arg, list(codes), kwargs))
        return ResolutionResult(tokens=list(codes), resolutions=[], elapsed_ms=0.0)

    # This attribute does not exist on the module today - `_extract_products`
    # still calls its own private `_canonical_product_code` per code, so this
    # setattr itself is expected to fail with AttributeError until D1 lands.
    monkeypatch.setattr(
        extract_service_mod, "resolve_references", _fake_resolve_references
    )

    with company_scope(db, frozenset({SORENTO})):
        AIExtractService(db)._extract_products(_parsed("SRT-A", "SRT-B", "SRT-C"))

    assert len(calls) == 1, "resolve_references must be called exactly once for the batch"
    _db_arg, codes, kwargs = calls[0]
    assert codes == ["SRT-A", "SRT-B", "SRT-C"]
    assert kwargs.get("enable_prefix_fallback") is False
    assert kwargs.get("enable_embedding_fallback") is False


# --------------------------------------------------------------------------- #
# S3 (code review): `resolve_references` TRUNCATES its own token list to
# `max_candidates` (`tokens = tokens[:max_candidates]`) rather than merely
# bounding the cost of its trigram "did you mean" pass, so a flat cap silently
# dropped code 101 onward. Chunked into batches of 100 instead - every call
# stays bounded (no line ceiling exists in the price tag / portal code to
# defer to for the chunk size), and every code still gets a call.
# --------------------------------------------------------------------------- #
def test_extract_products_chunks_a_long_batch_into_calls_of_100(db, monkeypatch):
    import app.services.ai_extract.extract_service as extract_service_mod
    from app.services.entity_resolver import ResolutionResult

    calls: list[tuple] = []

    def _fake_resolve_references(db_arg, codes, **kwargs):
        calls.append((db_arg, list(codes), kwargs))
        return ResolutionResult(tokens=list(codes), resolutions=[], elapsed_ms=0.0)

    monkeypatch.setattr(
        extract_service_mod, "resolve_references", _fake_resolve_references
    )

    codes = [f"SRT-{i}" for i in range(150)]
    with company_scope(db, frozenset({SORENTO})):
        AIExtractService(db)._extract_products(_parsed(*codes))

    assert len(calls) == 2, "150 codes must resolve as two chunked calls, not one truncated one"
    first_codes, first_kwargs = calls[0][1], calls[0][2]
    second_codes, second_kwargs = calls[1][1], calls[1][2]
    assert first_codes == codes[:100]
    assert second_codes == codes[100:]
    assert first_kwargs.get("max_candidates") == 100
    assert second_kwargs.get("max_candidates") == 50


def test_extract_products_resolves_all_150_codes_when_all_exist(db):
    codes = [unique_code(f"SRTCHUNK{i}") for i in range(150)]
    for code in codes:
        _product(db, code)

    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed(*codes))

    assert len(out) == 150
    assert all(row.match == "product" for row in out), [
        row.product_code for row in out if row.match != "product"
    ]
    assert [row.product_code for row in out] == codes


# --------------------------------------------------------------------------- #
# Security review: a resolver failure must not turn an LLM extract that
# already cost real money into a 500 on the public route - every code falls
# back to the documented D2 "no match" shape (raw text, no ids).
# --------------------------------------------------------------------------- #
def test_extract_products_falls_back_to_raw_codes_when_resolver_raises(db, monkeypatch):
    import app.services.ai_extract.extract_service as extract_service_mod

    def _boom(db_arg, codes, **kwargs):
        raise RuntimeError("ZZT resolver down")

    monkeypatch.setattr(extract_service_mod, "resolve_references", _boom)

    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._extract_products(_parsed("SRT-A", "SRT-B"))

    assert [row.product_code for row in out] == ["SRT-A", "SRT-B"]
    assert all(row.match is None for row in out)
    assert all(row.product_id is None and row.product_set_id is None for row in out)


# --------------------------------------------------------------------------- #
# Browser check: the router-level `apply_company_scope` dependency resolves a
# portal token to the CONTACT'S companies (plural - `RespondContactCompany`),
# not the ONE company this request belongs to. A code seeded in two of a
# multi-company contact's companies came back "ambiguous" (two scoped hits)
# under that wider ambient scope in the real portal, reading as Not Found for
# a product that genuinely exists. The other tests in this file all wrap
# `_extract_products` directly, under a hand-set `company_scope`, and so
# never exercised the ROUTE's own scope at all - this drives the real
# `POST /api/v1/public/portal/ai-extract` route through a TestClient instead.
# --------------------------------------------------------------------------- #
def test_route_scopes_the_extract_to_the_requests_own_company(monkeypatch):
    import json
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.models.access import RespondContact
    from app.models.company import RespondContactCompany
    from app.models.portal import PortalToken
    from app.services.llm_provider import ChatResult
    import app.services.ai_extract.extract_service as extract_service_mod
    from tests._portal_grant import grant_portal_forms

    with blank_session() as db:
        # SORENTO is the only ACTIVE company - `_resolve_company` (the portal
        # route's own company resolver, single-tenant stub) picks the first
        # active company with no further tiebreak, so this keeps the
        # assertion below deterministic rather than racing an unordered
        # `.first()` between two equally-active rows. The contact still
        # genuinely belongs to BOTH (`RespondContactCompany` below), which is
        # the ambient scope this test is reproducing the bug against.
        if db.query(Company).filter(Company.id == SORENTO).first() is None:
            db.add(
                Company(id=SORENTO, name="ZZT Sorento", code=unique_code("SRT")[:20], is_active=True)
            )
        else:
            # A default company already seeded for this schema (the app's own
            # startup path) - make sure it is the sole ACTIVE row this test
            # relies on rather than assuming its flag.
            db.query(Company).filter(Company.id == SORENTO).update({"is_active": True})
        other = str(uuid.uuid4())
        db.add(Company(id=other, name="ZZT Other Co", code=unique_code("OTH")[:20], is_active=False))
        db.flush()

        contact = RespondContact(
            id=str(uuid.uuid4()),
            phone_number=f"+6011{uuid.uuid4().hex[:8]}",
            name="ZZT multi-company contact",
        )
        db.add(contact)
        db.flush()
        db.add(RespondContactCompany(id=_uid(), respond_contact_id=contact.id, company_id=SORENTO))
        db.add(RespondContactCompany(id=_uid(), respond_contact_id=contact.id, company_id=other))
        grant_portal_forms(db, contact.id, ["price_tag_request"])
        db.flush()

        code = "SRT6536-DIY"
        sorento_product = _product(db, code, company_id=SORENTO)
        _product(db, code, company_id=other)

        token = PortalToken(
            id=str(uuid.uuid4()),
            token=f"ZZT-tok-{uuid.uuid4().hex}",
            contact_id=contact.id,
            space_id="ZZT-space",
            expires_at=datetime.utcnow() + timedelta(days=30),
            verified_at=datetime.utcnow() - timedelta(minutes=5),
        )
        db.add(token)
        db.commit()

        def _override_get_db():
            yield db

        content = json.dumps(
            {"products": [{"product_code": code, "product_name": "raw", "quantity": 1}]}
        )

        class _FakeProvider:
            def chat(self, **kwargs):
                return ChatResult(
                    content=content, prompt_tokens=0, completion_tokens=0, total_tokens=0
                )

        def _fake_resolve_provider(self):
            return _FakeProvider(), "openai", "gpt-4"

        monkeypatch.setattr(
            extract_service_mod.AIExtractService,
            "_resolve_provider",
            _fake_resolve_provider,
        )

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                res = c.post(
                    "/api/v1/public/portal/ai-extract",
                    data={"form_key": "portal.price_tag_request"},
                    files=[("files", ("so.txt", code.encode(), "text/plain"))],
                    headers={"X-Portal-Token": token.token},
                )
        finally:
            app.dependency_overrides.clear()

        assert res.status_code == 200, res.text
        products = res.json()["products"]
        assert len(products) == 1
        # Under the FULL ambient (both-company) scope this reads "ambiguous" -
        # two scoped hits, match=None. Narrowed to the request's own company,
        # it resolves to exactly the SORENTO row.
        assert products[0]["match"] == "product"
        assert products[0]["product_id"] == sorento_product.id
