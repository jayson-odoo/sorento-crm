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
