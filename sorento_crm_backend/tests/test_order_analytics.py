"""Service + endpoint tests for order aggregation analytics.

Covers GET /api/v1/order-management/orders/analytics and
OrderService.order_analytics - the analytical-question gap closer:
 - metric=count / total_value / avg_delivery_days happy paths
 - group_by=customer / product / month bucketing
 - total_value falls back to line totals when the order header total_amount is 0
    (this dataset never populates orders.total_amount)
 - avg_delivery_days computes the correct day difference and is non-negative
 - validation: unknown metric / group_by raise 422 (AppException)
 - endpoint enforces auth (401/403 with no principal)

Runs against the live Postgres test DB: seed rows with a unique order_number
prefix, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.order import Customer, Order, OrderLine
from app.models.product import Product
from app.models.inventory import Warehouse
from app.services.error_handler import AppException
from app.services.order_service import OrderService

PREFIX = "OANLY-"
CUSTOMER_NAME = "OANLY TEST CUSTOMER SDN BHD"


def _cleanup() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(
                text(
                    "DELETE FROM order_lines WHERE order_id IN "
                    "(SELECT id FROM orders WHERE order_number LIKE 'OANLY-%')"
                )
            )
            conn.execute(text("DELETE FROM orders WHERE order_number LIKE 'OANLY-%'"))
            conn.execute(
                text("DELETE FROM customers WHERE customer_name = :n"),
                {"n": CUSTOMER_NAME},
            )
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(db: Session):
    """Seed one customer + three orders.

    o1: order_date 2026-01-01, delivered +2 days, header total_amount 100
    o2: order_date 2026-01-10, delivered +4 days, header total_amount 300
    o3: order_date 2026-02-05, NOT delivered,     header total_amount 0 but a
        line total of 50 (exercises the line-total fallback + product grouping)
    """
    cust = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"{PREFIX}C1",
        customer_name=CUSTOMER_NAME,
    )
    db.add(cust)
    db.flush()

    o1 = Order(
        id=str(uuid.uuid4()),
        order_number=f"{PREFIX}0001",
        customer_id=cust.id,
        debtor_name=CUSTOMER_NAME,
        order_date=datetime(2026, 1, 1),
        actual_delivery_date=datetime(2026, 1, 3),
        total_amount=100,
    )
    o2 = Order(
        id=str(uuid.uuid4()),
        order_number=f"{PREFIX}0002",
        customer_id=cust.id,
        debtor_name=CUSTOMER_NAME,
        order_date=datetime(2026, 1, 10),
        actual_delivery_date=datetime(2026, 1, 14),
        total_amount=300,
    )
    o3 = Order(
        id=str(uuid.uuid4()),
        order_number=f"{PREFIX}0003",
        customer_id=cust.id,
        debtor_name=CUSTOMER_NAME,
        order_date=datetime(2026, 2, 5),
        total_amount=0,
    )
    db.add_all([o1, o2, o3])
    db.flush()

    product = db.query(Product).first()
    warehouse = db.query(Warehouse).first()
    assert product and warehouse, "test DB needs at least one product + warehouse"
    db.add(
        OrderLine(
            id=str(uuid.uuid4()),
            order_id=o3.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=1,
            total=50,
        )
    )
    db.commit()
    return cust, [o1, o2, o3], product


def test_count_scoped_to_customer(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(metric="count", customer_ids=[str(cust.id)])
    assert res["total"]["value"] == 3
    assert res["empty"] is False


def test_total_value_sums_header_and_line_fallback(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(
        metric="total_value", customer_ids=[str(cust.id)]
    )
    # 100 + 300 (headers) + 50 (o3 line fallback, header is 0) = 450
    assert res["total"]["value"] == 450.0


def test_total_value_date_window(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(
        metric="total_value",
        customer_ids=[str(cust.id)],
        date_from=datetime(2026, 1, 1),
        date_to=datetime(2026, 1, 31, 23, 59, 59),
    )
    # Only o1 + o2 fall in January → 100 + 300 = 400 (o3 is February).
    assert res["total"]["value"] == 400.0
    assert res["total"]["order_count"] == 2


def test_avg_delivery_days_computed(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(
        metric="avg_delivery_days", customer_ids=[str(cust.id)]
    )
    # o1=2 days, o2=4 days, o3 has no delivery date and is excluded → avg 3.
    assert res["total"]["value"] == 3.0
    assert res["total"]["value"] >= 0


def test_group_by_customer(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(
        metric="total_value", group_by="customer", customer_ids=[str(cust.id)]
    )
    assert res["group_by"] == "customer"
    labels = {g["group_label"] for g in res["groups"]}
    assert CUSTOMER_NAME in labels
    row = next(g for g in res["groups"] if g["group_label"] == CUSTOMER_NAME)
    assert row["value"] == 450.0


def test_group_by_month(db: Session) -> None:
    cust, _, _ = _seed(db)
    res = OrderService(db).order_analytics(
        metric="count", group_by="month", customer_ids=[str(cust.id)]
    )
    by_month = {g["group_key"]: g["value"] for g in res["groups"]}
    assert by_month.get("2026-01") == 2
    assert by_month.get("2026-02") == 1


def test_group_by_product_ranked(db: Session) -> None:
    cust, _, product = _seed(db)
    res = OrderService(db).order_analytics(
        metric="count", group_by="product", customer_ids=[str(cust.id)]
    )
    assert res["group_by"] == "product"
    keys = {g["group_key"] for g in res["groups"]}
    assert product.product_code in keys


def test_bad_metric_raises_422(db: Session) -> None:
    with pytest.raises(AppException) as exc:
        OrderService(db).order_analytics(metric="bogus")
    assert exc.value.status_code == 422


def test_bad_group_by_raises_422(db: Session) -> None:
    with pytest.raises(AppException) as exc:
        OrderService(db).order_analytics(metric="count", group_by="galaxy")
    assert exc.value.status_code == 422


def test_endpoint_requires_auth() -> None:
    with TestClient(app) as client:
        res = client.get("/api/v1/order-management/orders/analytics?metric=count")
    assert res.status_code in (401, 403), res.text
