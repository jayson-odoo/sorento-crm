"""Fix round 4, BUG A - ORM metadata drift vs migration 305.

`units_of_measure.uom_code`, `warehouses.warehouse_code`,
`product_categories.category_code` and `suppliers.supplier_code` still
declared `unique=True` on the column, which makes `create_all` (every scratch
lane, CI) rebuild the GLOBAL single-column unique migration 305 already
replaced in production with `UNIQUE (company_id, <code>)`. A second company
therefore could not hold the same warehouse/uom/category/supplier code -
live repro: a SIM push of uom `UNIT` and 14 warehouses hit `UniqueViolation`.

No migration: production already carries the composite constraints (305).
This only aligns `create_all`'s output with what 305 already built, so a
scratch schema stops disagreeing with production about what is unique.

Substrate: `blank_session()` (a real `create_all` schema), so the assertion
is genuinely about what the ORM metadata builds, not about the real
prod-copy database (which already has 305 applied and would hide this).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.procurement import Supplier
from app.models.product import ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTCOMPU"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def other_company(db) -> str:
    company = Company(
        id=str(uuid.uuid4()),
        name=f"{MARKER} B",
        code=unique_code(MARKER)[:10],
    )
    db.add(company)
    db.flush()
    return str(company.id)


class TestWarehouseCodeIsUniquePerCompany:
    def test_the_same_code_exists_under_two_companies(self, db, other_company):
        code = unique_code(MARKER)[:20]
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code,
                          warehouse_name="A", company_id=DEFAULT_COMPANY_ID))
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code,
                          warehouse_name="B", company_id=other_company))
        db.flush()

        # Raw SQL, not `db.query()` - the ambient company-scope filter would
        # otherwise hide the second company's row, and which company a row
        # landed in is the very thing under test here.
        rows = db.execute(
            text("SELECT company_id FROM warehouses WHERE warehouse_code = :c"),
            {"c": code},
        ).scalars().all()
        assert {str(r) for r in rows} == {DEFAULT_COMPANY_ID, other_company}

    def test_the_same_code_twice_in_one_company_is_an_integrity_error(self, db):
        code = unique_code(MARKER)[:20]
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code,
                          warehouse_name="A", company_id=DEFAULT_COMPANY_ID))
        db.flush()
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code,
                          warehouse_name="A2", company_id=DEFAULT_COMPANY_ID))
        with pytest.raises(IntegrityError):
            db.flush()


class TestUomCodeIsUniquePerCompany:
    def test_the_same_code_exists_under_two_companies(self, db, other_company):
        code = unique_code(MARKER)[:20]
        db.add(UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code,
                              uom_name="A", company_id=DEFAULT_COMPANY_ID))
        db.add(UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code,
                              uom_name="B", company_id=other_company))
        db.flush()

        rows = db.execute(
            text("SELECT company_id FROM units_of_measure WHERE uom_code = :c"),
            {"c": code},
        ).scalars().all()
        assert {str(r) for r in rows} == {DEFAULT_COMPANY_ID, other_company}

    def test_the_same_code_twice_in_one_company_is_an_integrity_error(self, db):
        code = unique_code(MARKER)[:20]
        db.add(UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code,
                              uom_name="A", company_id=DEFAULT_COMPANY_ID))
        db.flush()
        db.add(UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code,
                              uom_name="A2", company_id=DEFAULT_COMPANY_ID))
        with pytest.raises(IntegrityError):
            db.flush()


class TestCategoryCodeIsUniquePerCompany:
    def test_the_same_code_exists_under_two_companies(self, db, other_company):
        code = unique_code(MARKER)[:20]
        db.add(ProductCategory(id=str(uuid.uuid4()), category_code=code,
                                category_name="A", company_id=DEFAULT_COMPANY_ID))
        db.add(ProductCategory(id=str(uuid.uuid4()), category_code=code,
                                category_name="B", company_id=other_company))
        db.flush()

        rows = db.execute(
            text("SELECT company_id FROM product_categories WHERE category_code = :c"),
            {"c": code},
        ).scalars().all()
        assert {str(r) for r in rows} == {DEFAULT_COMPANY_ID, other_company}

    def test_the_same_code_twice_in_one_company_is_an_integrity_error(self, db):
        code = unique_code(MARKER)[:20]
        db.add(ProductCategory(id=str(uuid.uuid4()), category_code=code,
                                category_name="A", company_id=DEFAULT_COMPANY_ID))
        db.flush()
        db.add(ProductCategory(id=str(uuid.uuid4()), category_code=code,
                                category_name="A2", company_id=DEFAULT_COMPANY_ID))
        with pytest.raises(IntegrityError):
            db.flush()


class TestSupplierCodeIsUniquePerCompany:
    def test_the_same_code_exists_under_two_companies(self, db, other_company):
        code = unique_code(MARKER)[:20]
        db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code,
                         supplier_name="A", company_id=DEFAULT_COMPANY_ID))
        db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code,
                         supplier_name="B", company_id=other_company))
        db.flush()

        rows = db.execute(
            text("SELECT company_id FROM suppliers WHERE supplier_code = :c"),
            {"c": code},
        ).scalars().all()
        assert {str(r) for r in rows} == {DEFAULT_COMPANY_ID, other_company}

    def test_the_same_code_twice_in_one_company_is_an_integrity_error(self, db):
        code = unique_code(MARKER)[:20]
        db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code,
                         supplier_name="A", company_id=DEFAULT_COMPANY_ID))
        db.flush()
        db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code,
                         supplier_name="A2", company_id=DEFAULT_COMPANY_ID))
        with pytest.raises(IntegrityError):
            db.flush()
