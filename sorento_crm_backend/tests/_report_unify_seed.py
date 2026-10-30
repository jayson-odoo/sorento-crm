"""Seed helpers shared by the REPORT-UNIFY slice 1 tests (not a test module).

Every row is seeded here: CI's database holds none. Specs are seeded the way production
holds them: a `product_spec_registry` row per key and one `product_specifications` row per
product whose `values` is `{key: {"value": ..., "unit": ...}}`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.access import SpecVisibilityPolicy
from app.models.order import OrderStatus
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._sales_report_do_seed import product


def registry_row(db, key, label, *, data_type="enum", unit=None, value_labels=None) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        id=str(uuid.uuid4()),
        spec_key=key,
        label=label,
        data_type=data_type,
        unit=unit,
        value_labels=value_labels or {},
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def seed_registry(db) -> None:
    """`trap_type` (enum, "Trap type", p_trap -> "P-trap") and `length` (numeric, mm)."""
    registry_row(
        db, "trap_type", "Trap type",
        value_labels={"p_trap": "P-trap", "s_trap": "S-trap", "wall": "Wall trap"},
    )
    registry_row(db, "length", "Length", data_type="numeric", unit="mm")


def set_specs(db, prod, values: dict) -> None:
    """The product's spec row. Plain values are wrapped as `{"value": v}`; a tuple is
    `(value, unit)`."""
    wrapped = {}
    for key, raw in values.items():
        if isinstance(raw, tuple):
            wrapped[key] = {"value": raw[0], "unit": raw[1]}
        else:
            wrapped[key] = {"value": raw}
    db.add(
        ProductSpecifications(
            id=str(uuid.uuid4()), product_id=prod.id, values=wrapped, provenance={}, rendered_text="ZZT",
        )
    )
    db.flush()


def make_product(db, code, *, category=None, brand=None, specs=None) -> Product:
    row = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
    if category is not None:
        row.category_id = category.id
    if brand is not None:
        row.brand_id = brand.id
    db.flush()
    if specs is not None:
        set_specs(db, row, specs)
    return row


def bulk_products(db, n, *, prefix, specs) -> list[Product]:
    """`n` products sharing one category and uom (cheap), each with the same `specs`."""
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("BC")[:50], category_name="Bulk",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=unique_code("BU")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID,
    )
    db.add_all([cat, uom])
    db.flush()
    rows = [
        Product(
            id=str(uuid.uuid4()), product_code=f"{prefix}-{i:03d}", product_name=f"{prefix}-{i:03d}",
            category_id=cat.id, base_uom_id=uom.id, list_price=Decimal("0"), is_active=True,
            company_id=DEFAULT_COMPANY_ID,
        )
        for i in range(n)
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        set_specs(db, row, specs)
    return rows


def hide_spec_keys(db, contact, keys) -> SpecVisibilityPolicy:
    """A contact-tier spec visibility policy that hides exactly `keys`."""
    row = SpecVisibilityPolicy(
        id=str(uuid.uuid4()), contact_id=contact.id, segment_code=None, spec_keys=None,
        excluded_spec_keys=list(keys),
    )
    db.add(row)
    db.flush()
    return row


def delivered_status(db) -> OrderStatus:
    """The order status `order_service._delivered_status_ids` counts as delivered."""
    row = db.query(OrderStatus).filter(OrderStatus.status_code == "delivered").first()
    if row is None:
        row = OrderStatus(id=str(uuid.uuid4()), status_code="delivered", status_name="Delivered", sequence=0)
        db.add(row)
        db.flush()
    return row


def mark_delivered(db, do_row, when, *, with_date=True) -> None:
    """A DO that counts as delivered: delivered status AND an actual delivery date."""
    do_row.order_status_id = delivered_status(db).id
    do_row.actual_delivery_date = when if with_date else None
    db.flush()
