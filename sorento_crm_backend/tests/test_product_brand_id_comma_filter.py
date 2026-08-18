"""AC-10: the products list ``brand_id`` filter accepts a comma-separated list.

A single value keeps the pre-existing behaviour (exact match, resolved through
``resolve_identifier``); several values union with ``IN``. Combined with
``discontinued_batch_id`` this is exactly what the product-discontinued deep
link needs: a recipient's brand-filtered subset of one company's batch.

Covers ``ProductService.list_products`` directly (the two routes - ``GET /`` and
``GET /neighbours`` - both delegate to it via the same ``brand_id`` param, so a
service-level test exercises the shared code path both routes rely on).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code=unique_code("CAT"), category_name="ZZT Category"))
        db.add(UnitOfMeasure(id=uom, uom_code=unique_code("EA")[:16], uom_name="ZZT Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _brand(db, name: str) -> str:
    b = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code(name[:4]),
        brand_name=f"ZZT {name}",
        is_active=True,
        company_id=SORENTO,
    )
    db.add(b)
    db.flush()
    return str(b.id)


def _product(db, *, code: str, brand_id: str | None, batch_id: str | None = None):
    cat, uom = _refs(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=cat,
        base_uom_id=uom,
        list_price=10,
        is_active=True,
        brand_id=brand_id,
        discontinued_notify_batch_id=batch_id,
    )
    db.add(p)
    return p


def _codes(payload) -> set[str]:
    return {p.product_code for p in payload["data"]}


def test_single_brand_id_behaves_exactly_as_before(db):
    brand_a = _brand(db, "A")
    brand_b = _brand(db, "B")
    _product(db, code="ZZT-A", brand_id=brand_a)
    _product(db, code="ZZT-B", brand_id=brand_b)
    db.commit()

    result = ProductService(db).list_products(brand_id=brand_a, limit=50)

    assert _codes(result) == {"ZZT-A"}


def test_comma_separated_brand_ids_union_with_in(db):
    brand_a = _brand(db, "A")
    brand_b = _brand(db, "B")
    brand_c = _brand(db, "C")
    _product(db, code="ZZT-A", brand_id=brand_a)
    _product(db, code="ZZT-B", brand_id=brand_b)
    _product(db, code="ZZT-C", brand_id=brand_c)
    db.commit()

    result = ProductService(db).list_products(brand_id=f"{brand_a},{brand_b}", limit=50)

    assert _codes(result) == {"ZZT-A", "ZZT-B"}


def test_comma_separated_with_whitespace_and_an_unknown_id_narrows_not_empties(db):
    brand_a = _brand(db, "A")
    _product(db, code="ZZT-A", brand_id=brand_a)
    db.commit()
    unknown = str(uuid.uuid4())

    result = ProductService(db).list_products(brand_id=f" {brand_a} , {unknown} ", limit=50)

    assert _codes(result) == {"ZZT-A"}


def test_combined_discontinued_batch_and_multi_brand_returns_exact_subset(db):
    """The exact shape the product-discontinued deep link relies on."""
    brand_a = _brand(db, "A")
    brand_b = _brand(db, "B")
    brand_c = _brand(db, "C")
    batch = str(uuid.uuid4())
    other_batch = str(uuid.uuid4())
    _product(db, code="ZZT-A", brand_id=brand_a, batch_id=batch)
    _product(db, code="ZZT-B", brand_id=brand_b, batch_id=batch)
    _product(db, code="ZZT-C", brand_id=brand_c, batch_id=batch)  # not in recipient's scope
    _product(db, code="ZZT-OTHER-BATCH", brand_id=brand_a, batch_id=other_batch)
    db.commit()

    result = ProductService(db).list_products(
        discontinued_batch_id=batch, brand_id=f"{brand_a},{brand_b}", limit=50
    )

    assert _codes(result) == {"ZZT-A", "ZZT-B"}
