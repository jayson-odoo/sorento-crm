"""Per-company natural-key uniqueness - AC-J1/J2 (composite unique indexes).

Migration 305 swapped every single-column natural-key unique (product_code,
order_number, warehouse_code, customer code/name, ...) for a composite
``(company_id, key)`` unique index. The business consequence:

  - AC-J1: two DIFFERENT companies may each own a row with the SAME code - they
    are distinct rows, not a conflict.
  - AC-J2: the SAME company still cannot hold two rows with that code.

Exercised through the ORM insert path (auto-stamp fills ``company_id`` from the
active scope) so both the stamp and the DB constraint are proven end-to-end.
Runs against the local Postgres dev DB inside a rolled-back SAVEPOINT; all rows
carry a ``zzuniq`` marker + a throwaway Mocha company, so nothing persists and no
unscoped cleanup is needed.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.services.company_scope import register_company_scope_listeners

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def mocha(db: Session) -> str:
    suffix = uuid.uuid4().hex[:8]
    c = Company(id=str(uuid.uuid4()), name=f"ZZUNIQ Mocha {suffix}", code=f"ZUM{suffix}")
    db.add(c)
    db.flush()
    return c.id


def _seed_cat_uom(db: Session, company_id: str, suffix: str):
    cat_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": cat_id, "code": f"ZZUNIQ-CAT-{suffix}", "name": f"zzuniq cat {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": uom_id, "code": f"ZZUNIQ-UOM-{suffix}", "name": f"zzuniq uom {suffix}", "cid": company_id},
    )
    return cat_id, uom_id


# --------------------------------------------------------------------------- #
# product_code - composite (company_id, product_code)                          #
# --------------------------------------------------------------------------- #
def test_same_product_code_allowed_across_companies(db, mocha):
    from app.models.product import Product

    suffix = uuid.uuid4().hex[:8]
    code = f"ZZUNIQPROD{suffix}"
    cat_s, uom_s = _seed_cat_uom(db, SORENTO, f"{suffix}S")
    cat_m, uom_m = _seed_cat_uom(db, mocha, f"{suffix}M")

    def _mk(cat, uom):
        return Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=cat, base_uom_id=uom, list_price=1,
        )

    # AC-J1: Sorento + Mocha may BOTH own product code X (distinct rows).
    with company_scope(db, frozenset({SORENTO})):
        db.add(_mk(cat_s, uom_s))
        db.flush()
    with company_scope(db, frozenset({mocha})):
        db.add(_mk(cat_m, uom_m))
        db.flush()

    rows = db.execute(
        text("SELECT company_id FROM products WHERE product_code = :c"), {"c": code}
    ).all()
    assert {str(r[0]) for r in rows} == {SORENTO, mocha}


def test_duplicate_product_code_same_company_rejected(db, mocha):
    from app.models.product import Product

    suffix = uuid.uuid4().hex[:8]
    code = f"ZZUNIQPROD{suffix}"
    cat_m, uom_m = _seed_cat_uom(db, mocha, suffix)

    def _mk():
        return Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=cat_m, base_uom_id=uom_m, list_price=1,
        )

    with company_scope(db, frozenset({mocha})):
        db.add(_mk())
        db.flush()
        # AC-J2: a second row with the same code in the SAME company violates the
        # composite unique index.
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(_mk())
                db.flush()


# --------------------------------------------------------------------------- #
# order_number - composite (company_id, order_number)                          #
# --------------------------------------------------------------------------- #
def test_same_order_number_allowed_across_companies(db, mocha):
    from app.models.order import Order

    number = f"ZZUNIQ-SO-{uuid.uuid4().hex[:8]}"

    with company_scope(db, frozenset({SORENTO})):
        db.add(Order(id=str(uuid.uuid4()), order_number=number))
        db.flush()
    with company_scope(db, frozenset({mocha})):
        db.add(Order(id=str(uuid.uuid4()), order_number=number))
        db.flush()

    rows = db.execute(
        text("SELECT company_id FROM orders WHERE order_number = :n"), {"n": number}
    ).all()
    assert {str(r[0]) for r in rows} == {SORENTO, mocha}


def test_duplicate_order_number_same_company_rejected(db, mocha):
    from app.models.order import Order

    number = f"ZZUNIQ-SO-{uuid.uuid4().hex[:8]}"
    with company_scope(db, frozenset({mocha})):
        db.add(Order(id=str(uuid.uuid4()), order_number=number))
        db.flush()
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(Order(id=str(uuid.uuid4()), order_number=number))
                db.flush()
