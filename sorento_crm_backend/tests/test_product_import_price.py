"""Product list upload price coercion.

Bug: a ``list_price`` of -1 (a "no price" sentinel from the source system)
was rejected with a hard error and the row was skipped. It must instead be
coerced to 0 so the product still imports.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import product_service as product_service_mod
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Coercion of the price happens before any supplier/settings/embedding work.
    Stub those out: the embedding fan-out enqueues RQ jobs, and the
    default-supplier / lead-time lookups are irrelevant to price handling."""
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_resolve_default_supplier_for_new_product",
        lambda self: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_default_standard_lead_time_days",
        lambda self: None,
    )


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite over a hand-listed subset of the product tables.
    """
    with blank_session() as session:
        yield session


@pytest.fixture
def seeded(db):
    cat_id = str(uuid.uuid4())
    db.add(ProductCategory(id=cat_id, category_code="CAT1", category_name="Category One"))
    uom_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code="EA", uom_name="Each"))
    db.commit()
    return {"category_code": "CAT1", "uom_id": uom_id}


def _row(price):
    return {"product_code": "SKU-NEG", "product_name": "Neg", "item_group": "CAT1", "list_price": price}


@pytest.mark.parametrize("price", ["-1", "-0.01", -1])
def test_validate_negative_price_is_coerced_not_rejected(db, seeded, price):
    service = ProductService(db)
    result = service.validate_products_import([_row(price)])

    assert result["errors"] == []
    assert result["summary"]["would_create"] == 1


@pytest.mark.parametrize("price", ["-1", -1])
def test_import_negative_price_persists_zero(db, seeded, price):
    service = ProductService(db)
    result = service.bulk_import_products([_row(price)], user_id="user-1")

    assert result["errors"] == []
    assert result["created"] == 1
    product = db.query(Product).filter(Product.product_code == "SKU-NEG").one()
    assert product.list_price == Decimal("0")


def test_non_numeric_price_still_errors(db, seeded):
    service = ProductService(db)
    result = service.validate_products_import([_row("abc")])

    assert result["summary"]["would_create"] == 0
    assert any("valid number" in e for e in result["errors"])
