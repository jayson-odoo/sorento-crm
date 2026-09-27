"""No purchase order and no product import writes a supplier price (#1288, fix lane round 3).

Owner ruling on Q16 (27 Sep 2026, 15:31 MYT): "purchase order shouldn't do this la, product
excel import also shouldnt do this". The cost lists are the only source of a supplier cost.

Measured at the start of round 3 (plan section 7.5): neither path writes
`product_suppliers.unit_cost`/`currency` or `products.cost_price` today. The product import's
only price column (`list_price` / `Price`) is the selling price, and a PO save only writes its
own line's `unit_cost`. These tests pin that:

* R2: a product import row carrying every supplier price column name a person might add
  (`Cost Price`, `Unit Cost`, `Supplier Price`, `unit_cost`, `cost_price`, `currency`) leaves
  the link's price and the product's cost price alone, while every column the import does
  read still lands. The PO half (R1) is `tests/scm/test_po_never_writes_supplier_price.py`.
* R3: a source guard. Only the cost list code, the product-supplier CRUD and the owner-run
  backfill script may put a price on a `product_suppliers` row, so a new direct writer in a
  PO or import module goes red here instead of waiting for the daily tick to undo it.
"""
from __future__ import annotations

import ast
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import product_service as product_service_mod
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session

BACKEND = Path(__file__).resolve().parents[1]
USER_ID = "717677a2-1052-5fb1-9f10-981584261561"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def world(db, monkeypatch):
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZR3CAT", category_name="R3 Cat")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="EA", uom_name="Each")
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code="ZZR3SUP", supplier_name="R3 Ceramics",
        is_active=True,
    )
    db.add_all([cat, uom, supplier])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()), product_code="ZZR3-SKU", product_name="R3 basin",
        category_id=cat.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
        cost_price=Decimal("70.00"),
    )
    db.add(product)
    db.flush()
    link = ProductSupplier(
        id=str(uuid.uuid4()), product_id=product.id, supplier_id=supplier.id,
        standard_lead_time_days=30, unit_cost=Decimal("100.00"), currency="CNY",
    )
    db.add(link)
    db.commit()

    # The import links every product it touches to the default supplier; make that THIS
    # supplier so the import provably reaches the priced link. Embedding fan-out is RQ work.
    monkeypatch.setattr(
        product_service_mod.ProductService, "_resolve_default_supplier_for_new_product",
        lambda self: supplier,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService, "_default_standard_lead_time_days", lambda self: 30,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService, "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    return {"product": product, "link": link, "supplier": supplier}


_SUPPLIER_PRICE_COLUMNS = {
    "Cost Price": "11.00", "Unit Cost": "12.00", "Supplier Price": "13.00",
    "unit_cost": "14.00", "cost_price": "15.00", "currency": "USD",
}


def test_r2_product_import_never_writes_a_supplier_price(db, world):
    rows = [
        {"product_code": "ZZR3-SKU", "product_name": "R3 basin renamed",
         "item_group": "ZZR3CAT", "list_price": "150.00", **_SUPPLIER_PRICE_COLUMNS},
        {"product_code": "ZZR3-NEW", "product_name": "R3 new tap",
         "item_group": "ZZR3CAT", "list_price": "60.00", **_SUPPLIER_PRICE_COLUMNS},
    ]

    result = ProductService(db).bulk_import_products(rows, user_id=USER_ID)

    assert result["errors"] == []
    assert (result["created"], result["updated"]) == (1, 1)
    db.expire_all()

    # Every column the import reads still lands.
    existing = db.query(Product).filter(Product.product_code == "ZZR3-SKU").one()
    assert existing.product_name == "R3 basin renamed"
    assert existing.list_price == Decimal("150.00")
    new = db.query(Product).filter(Product.product_code == "ZZR3-NEW").one()
    assert new.list_price == Decimal("60.00")

    # No supplier price, anywhere.
    assert existing.cost_price == Decimal("70.00")
    assert new.cost_price is None
    link = db.query(ProductSupplier).filter(ProductSupplier.id == world["link"].id).one()
    assert (link.unit_cost, link.currency) == (Decimal("100.00"), "CNY")
    new_link = db.query(ProductSupplier).filter(ProductSupplier.product_id == new.id).one()
    assert (new_link.unit_cost, new_link.currency) == (None, None)


# --------------------------------------------------------------------------- source guard

#: The only files allowed to put a price on a `product_suppliers` row (plan section 7.5).
_ALLOWED_WRITERS = {
    # The cost lists: apply creates a bare link, then `refresh_link` sets the price in force.
    "app/services/procurement/supplier_cost_service.py",
    # The product-supplier CRUD routes (`ProductSupplierService`), gated on
    # `procurement.product_suppliers.add` / `.edit`.
    "app/services/procurement_service.py",
    # Owner-run one-off (S15, `--all-suppliers` fills a NULL link price from PO lines).
    # Not a PO save path; flagged on PR #1305 round 3 for the owner.
    "scripts/backfill_product_supplier_from_last_po.py",
    # Demo and simulation seeders: they build a fake catalogue on a dev database.
    "scripts/scm_sim/world.py",
    "scripts/seed_scm_demo.py",
    "scripts/seed_scm_live_demo.py",
}

#: Parameter names this codebase gives a `ProductSupplier` passed into a function.
_LINK_PARAM_NAMES = {"link", "ps", "product_supplier"}

_PRICE_KEYS = {"unit_cost", "currency"}
_RAW_SQL_WRITE = re.compile(
    r"(UPDATE\s+product_suppliers\b.*\b(unit_cost|currency)\b"
    r"|INSERT\s+INTO\s+product_suppliers\b.*\b(unit_cost|currency)\b)",
    re.IGNORECASE | re.DOTALL,
)


def _price_writes(tree: ast.AST) -> list[int]:
    """Lines where a `ProductSupplier(...)` is built with a price (or opaque `**kwargs`),
    a `ProductSupplier` query is bulk-updated with a price, or a raw SQL string writes a
    price onto `product_suppliers`."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name == "ProductSupplier" and any(
                kw.arg in _PRICE_KEYS or kw.arg is None for kw in node.keywords
            ):
                hits.append(node.lineno)
            # `db.query(ProductSupplier)...update({"unit_cost": ...})`
            if name == "update" and isinstance(fn, ast.Attribute) \
                    and "ProductSupplier" in ast.unparse(fn.value) \
                    and any(k in ast.unparse(a) for a in node.args for k in _PRICE_KEYS):
                hits.append(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _RAW_SQL_WRITE.search(node.value):
                hits.append(node.lineno)
    return hits


def _link_price_assignments(tree: ast.AST) -> list[int]:
    """`<x>.unit_cost = ...` / `<x>.currency = ...` where `<x>` was bound from a
    `ProductSupplier` query or constructor in the same function, or passed in under one of
    `_LINK_PARAM_NAMES`."""
    hits: list[int] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        link_names = {
            a.arg for a in fn.args.args + fn.args.kwonlyargs if a.arg in _LINK_PARAM_NAMES
        }
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and "ProductSupplier" in ast.unparse(node.value):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        link_names.add(t.id)
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) \
                    and "ProductSupplier" in ast.unparse(node.iter):
                link_names.add(node.target.id)
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and t.attr in _PRICE_KEYS \
                            and isinstance(t.value, ast.Name) and t.value.id in link_names:
                        hits.append(node.lineno)
    return hits


def test_r3_only_the_cost_lists_and_the_crud_write_a_link_price():
    offenders: dict[str, list[int]] = {}
    for root in ("app", "scripts"):
        for path in sorted((BACKEND / root).rglob("*.py")):
            rel = path.relative_to(BACKEND).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            lines = _price_writes(tree) + _link_price_assignments(tree)
            if lines and rel not in _ALLOWED_WRITERS:
                offenders[rel] = sorted(set(lines))
    assert offenders == {}, (
        "A new writer puts a supplier price on product_suppliers outside the cost lists "
        f"(owner ruling on Q16, 27 Sep 2026): {offenders}"
    )


def test_r3_the_guard_sees_the_writers_it_allows():
    """The guard is only worth something if it would see a writer: each allowed file is
    actually caught by it, so a pattern that silently matches nothing fails here."""
    for rel in sorted(_ALLOWED_WRITERS):
        tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8"), filename=rel)
        assert _price_writes(tree) + _link_price_assignments(tree), rel
