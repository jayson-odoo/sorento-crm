"""REPORT-SMART-L one ranking, round R0 (AC-OR0): a bare count is never a code holding it.

Owner turn: "Top 100 selling item this year by product, delivered qty" got a Candidates line
'"100": code M1100 / M2100 / M3100, holding "100"' and the parser chose stock. A bare number is
a count or a size, never a code fragment the candidates offer. A word with letters and digits
still gets its candidates, and the resolver still answers a bare partial number through its
substring tier after the parse. Fake codes only.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.chatbot.head import candidates
from app.services.company_scope import DEFAULT_COMPANY_ID, company_scope, register_company_scope_listeners
from app.services.product_code_resolution import resolve_codes_to_products
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _products(db, *codes: str) -> None:
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    for code in codes:
        db.add(Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name of {code}", category_id=cat.id,
            base_uom_id=uom.id, list_price=1, company_id=DEFAULT_COMPANY_ID, is_searchable=True))
    db.flush()


def _lines(db, message: str) -> list[str]:
    return candidates.candidate_lines(candidates.shortlist(db, message))


OWNER_TURN = "Top 100 selling item this year by product, delivered qty"


def test_or0_a_bare_count_is_not_offered_as_a_code_holding_it(db) -> None:
    _products(db, "ZZM1100", "ZZM2100", "ZZM3100")
    lines = _lines(db, OWNER_TURN)
    assert not any("ZZM1100" in ln or "ZZM2100" in ln or "ZZM3100" in ln for ln in lines), lines
    assert not any(ln.startswith('- "100"') for ln in lines), lines


def test_or0_near_miss_a_word_with_letters_and_digits_still_gets_its_candidates(db) -> None:
    _products(db, "ZZCB6635-NL", "ZZSRT102-RG")
    cb = _lines(db, "stock of cb6635")
    assert any("ZZCB6635-NL" in ln for ln in cb), cb
    srt = _lines(db, "stock of srt102-rg")
    assert any("ZZSRT102-RG" in ln for ln in srt), srt


def test_or0_near_miss_a_product_whose_code_is_exactly_the_number_is_still_listed_as_that_code(db) -> None:
    _products(db, "100", "ZZM1100")
    lines = _lines(db, OWNER_TURN)
    assert any(ln.startswith('- "100"') and "code 100 " in ln for ln in lines), lines


def test_or0_near_miss_the_resolver_still_answers_a_bare_partial_number_after_the_parse(db) -> None:
    _products(db, "ZZSRTWC8518-SH", "ZZOTHER-1")
    with company_scope(db, frozenset({DEFAULT_COMPANY_ID})):
        result = resolve_codes_to_products(db, ["8518"])
    assert {m.product.product_code for m in result.matches} == {"ZZSRTWC8518-SH"}, result.matches
