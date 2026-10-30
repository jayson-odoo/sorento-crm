"""SO-LINE-DESC AC-9: the migration that adds `products.show_so_line_description` ticks every
product with code RPACC (any company) and no other. Run on a scratch schema (CI's DB has no data).

The scratch schema is built from the models, so the new columns already exist there: the test
drops them, then runs the migration's own `upgrade()`, which must add them back and set the data.
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import blank_session, unique_code

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration():
    found = [p for p in VERSIONS.glob("*.py") if "show_so_line_description" in p.read_text()]
    assert len(found) == 1, f"expected one migration adding show_so_line_description: {found}"
    spec = importlib.util.spec_from_file_location("m_so_line_desc", found[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _company(db) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO companies (id, name, code, is_active) VALUES (:i, :n, :c, true)"),
        {"i": cid, "n": unique_code("SLD"), "c": unique_code("SL")[:20]},
    )
    return cid


def _product(db, code, company_id, category, uom):
    row = Product(
        id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("1.00"),
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def test_ac9_only_rpacc_is_ticked_in_every_company_after_the_migration():
    module = _migration()
    with blank_session() as db:
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("u")[:20], uom_name="Unit")
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("c"), category_name="ZZT cat"
        )
        db.add_all([uom, cat])
        db.flush()
        company_a, company_b = _company(db), _company(db)
        wanted = {
            _product(db, "RPACC", company_a, cat, uom).id: True,
            _product(db, "RPACC", company_b, cat, uom).id: True,
            _product(db, "RPAC", company_a, cat, uom).id: False,
            _product(db, "RPBK", company_a, cat, uom).id: False,
            _product(db, "RPACC-X", company_a, cat, uom).id: False,
        }
        db.execute(text("ALTER TABLE products DROP COLUMN IF EXISTS show_so_line_description"))
        db.execute(text("ALTER TABLE sales_order_lines DROP COLUMN IF EXISTS description"))

        with Operations.context(MigrationContext.configure(db.connection())):
            module.upgrade()

        got = dict(
            db.execute(text("SELECT id, show_so_line_description FROM products")).all()
        )
        assert {str(k): v for k, v in got.items() if str(k) in wanted} == {
            str(k): v for k, v in wanted.items()
        }
        assert sum(1 for v in got.values() if v) == 2
        column = db.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema = "
                "current_schema() AND table_name = 'sales_order_lines' AND column_name = 'description'"
            )
        ).scalar()
        assert column == "YES"
