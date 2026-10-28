"""FILTER-MULTISELECT PR5 guard: the SCM dashboard's placed-PO tiles (`_placed_po_rows` feeds warehouses, suppliers and
rollups) take several suppliers and several categories (OR within a filter, AND across). Asserted through the
rollups tile's `incoming_po_count`. Seeded inside a rolled-back transaction on the real schema (the dashboard reads
views over real tables) and narrowed with `q=<unique tag>`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import pg_session, unique_code

ROLLUPS = "/api/v1/scm/dashboard/rollups"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


@pytest.fixture
def world(db):
    tag = unique_code("TIL", alpha=True)
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u"), uom_name="ZZT uom")
    cats = [ProductCategory(id=_uid(), category_code=unique_code(f"c{i}", alpha=True), category_name=f"ZZT cat {i}") for i in range(3)]
    sups = [Supplier(id=_uid(), supplier_code=unique_code(f"s{i}", alpha=True), supplier_name=f"ZZT sup {i}") for i in range(3)]
    db.add(uom)
    db.add_all(cats + sups)
    db.flush()
    # PO key -> (supplier index, category index): four open placed POs.
    spec = {"p1": (0, 0), "p2": (1, 1), "p3": (2, 0), "p4": (0, 2)}
    for key, (si, ci) in spec.items():
        product = Product(id=_uid(), product_code=f"{tag}-{key}", product_name=f"{tag} {key}", category_id=cats[ci].id,
                          base_uom_id=uom.id, list_price=Decimal("1.00"))
        db.add(product)
        db.flush()
        po = PurchaseOrder(id=_uid(), po_number=f"{tag}-{key}", status="active", supplier_id=sups[si].id)
        db.add(po)
        db.flush()
        db.add(PurchaseOrderLine(id=_uid(), purchase_order_id=po.id, product_id=product.id, qty_ordered=Decimal("10"),
                                 qty_received=Decimal("0"), line_status="open"))
    db.flush()
    return dict(tag=tag, sups=[s.supplier_code for s in sups], cats=[c.id for c in cats])


def _count(client, w, *pairs):
    resp = get(client, ROLLUPS, [("q", w["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()["incoming_po_count"]


def test_no_filter_counts_every_placed_po(client, world):
    assert _count(client, world) == 4


def test_suppliers_union_comma_joined_and_repeated(client, world):
    s0, s1, s2 = world["sups"]
    assert _count(client, world, ("supplier", s1)) == 1
    assert _count(client, world, ("supplier", f"{s0},{s1}")) == 3
    assert _count(client, world, ("supplier", s1), ("supplier", s2)) == 2


def test_categories_union_comma_joined_and_repeated(client, world):
    c0, c1, c2 = world["cats"]
    assert _count(client, world, ("category_id", c1)) == 1
    assert _count(client, world, ("category_id", f"{c0},{c1}")) == 3
    assert _count(client, world, ("category_id", c1), ("category_id", c2)) == 2


def test_suppliers_and_categories_and_across(client, world):
    s0, s1, s2 = world["sups"]
    c0, c1, c2 = world["cats"]
    # suppliers s0,s1 -> p1,p2,p4; categories c0,c1 -> p1,p2,p3; both -> p1,p2
    assert _count(client, world, ("supplier", f"{s0},{s1}"), ("category_id", f"{c0},{c1}")) == 2
