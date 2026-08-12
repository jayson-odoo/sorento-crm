"""Product list upload auto-creates its master-data references.

Before this, an Item Group / Item Brand that did not already exist as a
category / brand skipped the row ("no category found for item_group 'X'"), so
importing a fresh stock item list meant hand-creating ~90 categories and a
dozen brands first. The import now creates what it cannot find:

  * Item Group   -> product_categories (code = name = the raw value)
  * Item Brand   -> brands            (code = name = the raw value)
  * UOM / Unit   -> units_of_measure  (optional column; falls back to EA)

Values are matched case-insensitively against the existing code AND name, so a
re-import of the same file creates nothing the second time.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services import product_service as product_service_mod
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Reference auto-create happens before supplier/embedding work; stub those
    out (embeddings enqueue RQ jobs, suppliers are irrelevant here)."""
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
    with blank_session() as session:
        yield session


@pytest.fixture
def uom(db):
    """A pre-existing default UOM, so tests that are not about UOM creation
    don't also exercise the EA bootstrap."""
    row = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="EA", uom_name="Each")
    db.add(row)
    db.commit()
    return row


USER_ID = str(uuid.uuid4())


def _row(code: str, **over):
    row = {
        "Item Code": code,
        "Description": f"desc {code}",
        "Item Group": "SRT-FT",
        "Item Brand": "SORENTO",
        "Price": "10",
        "Is Active": "T",
    }
    row.update(over)
    return row


def test_unknown_item_group_creates_the_category(db, uom):
    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    assert result["created"] == 1
    assert result["created_categories"] == 1

    cat = db.query(ProductCategory).filter(ProductCategory.category_code == "SRT-FT").one()
    assert cat.category_name == "SRT-FT"
    assert cat.created_by == USER_ID
    product = db.query(Product).filter(Product.product_code == "P1").one()
    assert product.category_id == cat.id


def test_unknown_item_brand_creates_the_brand(db, uom):
    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    assert result["created_brands"] == 1

    brand = db.query(Brand).filter(Brand.brand_code == "SORENTO").one()
    assert brand.brand_name == "SORENTO"
    product = db.query(Product).filter(Product.product_code == "P1").one()
    assert product.brand_id == brand.id


def test_existing_category_and_brand_are_reused_case_insensitively(db, uom):
    db.add(ProductCategory(id=str(uuid.uuid4()), category_code="srt-ft", category_name="Floor Trap"))
    db.add(Brand(id=str(uuid.uuid4()), brand_code="sorento", brand_name="Sorento"))
    db.commit()

    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    assert result["created_categories"] == 0
    assert result["created_brands"] == 0
    assert db.query(ProductCategory).count() == 1
    assert db.query(Brand).count() == 1


def test_a_new_reference_is_created_once_for_the_whole_file(db, uom):
    rows = [_row("P1"), _row("P2"), _row("P3", **{"Item Group": "srt-ft"})]

    result = ProductService(db).bulk_import_products(rows, USER_ID)

    assert result["errors"] == []
    assert result["created"] == 3
    assert result["created_categories"] == 1
    assert result["created_brands"] == 1
    assert db.query(ProductCategory).count() == 1
    assert db.query(Brand).count() == 1


def test_uom_column_creates_the_uom_and_is_used_as_base_uom(db, uom):
    rows = [_row("P1", UOM="CTN"), _row("P2")]

    result = ProductService(db).bulk_import_products(rows, USER_ID)

    assert result["errors"] == []
    assert result["created_uoms"] == 1
    ctn = db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == "CTN").one()
    assert ctn.uom_name == "CTN"
    assert db.query(Product).filter(Product.product_code == "P1").one().base_uom_id == ctn.id
    # No UOM on the row -> the default (EA) still applies.
    assert db.query(Product).filter(Product.product_code == "P2").one().base_uom_id == uom.id


def test_default_uom_is_ea_even_when_other_uoms_exist(db):
    """Was: whatever row came back first (Liter on the Sorento data)."""
    db.add(UnitOfMeasure(id=str(uuid.uuid4()), uom_code="L", uom_name="Liter"))
    db.commit()

    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    ea = db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == "EA").one()
    assert db.query(Product).filter(Product.product_code == "P1").one().base_uom_id == ea.id


def test_default_uom_is_bootstrapped_when_the_company_has_none(db):
    result = ProductService(db).bulk_import_products([_row("P1")], USER_ID)

    assert result["errors"] == []
    assert result["created"] == 1
    ea = db.query(UnitOfMeasure).one()
    assert ea.uom_code == "EA"
    assert ea.uom_name == "Each"
    assert db.query(Product).filter(Product.product_code == "P1").one().base_uom_id == ea.id


def test_blank_item_group_still_skips_the_row(db, uom):
    """Nothing to create from an empty value, so the row is still rejected."""
    result = ProductService(db).bulk_import_products([_row("P1", **{"Item Group": ""})], USER_ID)

    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "item_group" in result["errors"][0]
    assert db.query(ProductCategory).count() == 0


def test_reference_longer_than_the_code_column_skips_the_row(db, uom):
    long_group = "G" * 51

    result = ProductService(db).bulk_import_products([_row("P1", **{"Item Group": long_group})], USER_ID)

    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "50" in result["errors"][0]
    assert db.query(ProductCategory).count() == 0


def test_validation_preview_reports_new_references_as_warnings_not_errors(db, uom):
    result = ProductService(db).validate_products_import([_row("P1"), _row("P2", UOM="CTN")])

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["summary"]["would_create"] == 2
    assert result["summary"]["new_categories"] == 1
    assert result["summary"]["new_brands"] == 1
    assert result["summary"]["new_uoms"] == 1
    joined = " | ".join(result["warnings"])
    assert "SRT-FT" in joined
    assert "SORENTO" in joined
    assert "CTN" in joined
