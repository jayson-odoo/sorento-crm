"""Hand-built plan fixtures for the reorder-revamp lane (PLAN-scm-reorder-revamp.md).

The same shape `tests/scm/test_m4_product_grain_confirm.py` established: an ORM chain
seeded row by row inside a rolled-back `pg_session`, never a `LIMIT 1` borrow off the
shared prod-copy database (CI's has no data). Every code is marker-prefixed so a stray
row is recognisable and no assertion can pick up a real record.

The engine is deliberately NOT run here. Every behaviour this lane adds reads or writes
frozen rows, so building the rows directly is both faster and pins the arithmetic under
test rather than the arithmetic that produced the fixture.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.models.inventory import Warehouse
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun

MARKER = "ZZTRVMP"


def u() -> str:
    return str(uuid.uuid4())


def code(stem: str = "") -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def category_and_uom(db):
    cat = ProductCategory(id=u(), category_code=code("CAT")[:40], category_name=code("cat"))
    uom = UnitOfMeasure(id=u(), uom_name=code("uom"), uom_code=code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    return cat, uom


def product(db, cat, uom, *, reorder_quantity: Optional[float] = None):
    p = Product(
        id=u(), product_code=code("SKU"), product_name="reorder revamp product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
        reorder_quantity=reorder_quantity,
    )
    db.add(p)
    db.flush()
    return p


def warehouse(db, *, segment: Optional[str] = None, pool_warehouse_id: Optional[str] = None):
    wh = Warehouse(
        id=u(), warehouse_code=code("WH")[:30], warehouse_name="wh", is_active=True,
        counts_as_available=True, segment=segment, pool_warehouse_id=pool_warehouse_id,
    )
    db.add(wh)
    db.flush()
    return wh


def supplier(db, name="supplier"):
    s = Supplier(id=u(), supplier_code=code("S")[:30], supplier_name=name)
    db.add(s)
    db.flush()
    return s


def run(db, *, grain: str = "product", legacy: bool = False, created_by: Optional[str] = "tester",
        warehouse_ids: Optional[list[str]] = None):
    r = ReorderRun(
        id=u(), status="completed", buy_scope="warehouse",
        decision_grain=(None if legacy else grain),
        front_planning_contract_version=(None if legacy else 1),
        started_at=datetime.utcnow(), created_by=created_by,
        warehouse_ids=warehouse_ids,
        source_system="scm", source_ref=code("RUN"),
    )
    db.add(r)
    db.flush()
    return r


def recommendation(db, plan, prod, wh, *, qty=50, sup=None, rec_type="buy",
                   inputs: Optional[dict] = None, unit_cost: Optional[float] = 12.0):
    rec = ReorderRecommendation(
        id=u(), run_id=plan.id, rec_type=rec_type, product_id=prod.id,
        warehouse_id=wh.id if wh is not None else None,
        rounded_qty=qty, recommended_qty=qty, status="proposed",
        supplier_id=(sup.id if sup else None), unit_cost=unit_cost, currency="MYR",
        inputs=inputs if inputs is not None else {"moq": 1, "order_multiple": 1},
    )
    db.add(rec)
    db.flush()
    return rec
