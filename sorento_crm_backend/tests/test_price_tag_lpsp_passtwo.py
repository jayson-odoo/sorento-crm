"""PRICETAG-LPSP fix round 2: crew hand-test findings on the paste resolver and the Item lookup.

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md (AC-14, AC-15, AC-17).

Bug 18: one extract that writes the SAME code in several spellings ("SRTMCB8083 BL",
"SRTMCB8083-BL", "srtmcb8083bl") resolved only one of them, because the resolver folds
spellings that normalise alike into one token. Every spelling must get the match.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.ai_extract.extract_service import AIExtractService
from tests import _ptag_combo_seed as combo_seed
from tests._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, code: str, *, list_price="100.00") -> Product:
    cat = ProductCategory(id=_uid(), category_code=f"c{_uid()[:12]}", category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"u{_uid()[:10]}", uom_name="Each")
    db.add_all([cat, uom])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=code,
        product_name=f"ZZT {code}",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=list_price,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- bug 18
def test_every_spelling_of_one_code_resolves_to_the_same_product(db):
    part = _product(db, "SRTZMCB8083-BL")
    spellings = ["SRTZMCB8083 BL", "SRTZMCB8083-BL", "srtzmcb8083bl"]
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._resolve_product_codes(spellings)
    assert set(out) == set(spellings)
    for spelling in spellings:
        code, kind, product_id, _set_id, _name = out[spelling]
        assert (code, kind, product_id) == ("SRTZMCB8083-BL", "product", part.id)


def test_every_spelling_of_one_missed_code_gets_the_suggestions(db):
    _product(db, "SRTZSUG8083-BL")
    spellings = ["SRTZSUG8083 BX", "srtzsug8083-bx"]
    suggestions: dict = {}
    with company_scope(db, frozenset({SORENTO})):
        out = AIExtractService(db)._resolve_product_codes(spellings, suggestions_out=suggestions)
    assert out == {}
    assert set(suggestions) == set(spellings)
    assert suggestions[spellings[0]] == suggestions[spellings[1]]


def test_a_part_repeated_across_two_plus_lines_resolves_on_both(db):
    host_a = _product(db, "SRTZRPA-HOST")
    host_b = _product(db, "SRTZRPB-HOST")
    shared = _product(db, "SRTZRP8083-BL")
    combo_a = combo_seed.combo(db, host_a, "a", parts=[{"product": shared}])
    combo_b = combo_seed.combo(db, host_b, "b", parts=[{"product": shared}])
    with company_scope(db, frozenset({SORENTO})):
        first, second = AIExtractService(db)._extract_products(
            {
                "products": [
                    {"product_code": "SRTZRPA-HOST", "set_codes": ["srtzrp8083 BL"]},
                    {"product_code": "SRTZRPB-HOST", "set_codes": ["SRTZRP8083-BL"]},
                ]
            }
        )
    assert [p.product_id for p in first.set_parts] == [shared.id]
    assert [p.product_id for p in second.set_parts] == [shared.id]
    assert first.combo_id == combo_a.id
    assert second.combo_id == combo_b.id
