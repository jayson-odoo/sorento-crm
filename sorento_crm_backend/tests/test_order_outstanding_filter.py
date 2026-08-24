"""Service tests for the CRM-003 `order_status` outstanding/delivered bucket filter.

`OrderService.list_orders(order_status=...)`:
 - 'delivered'   = status delivered/completed AND actual_delivery_date set
 - 'outstanding' = NOT delivered (New Order, Processing, Cancelled, or a delivery
    date under a non-delivered status - the flagged Status/date inconsistency)
 - None / '' / unknown = no filter (all rows), no regression
 - AND-combines with the existing customer_ids filter
 - the two buckets partition the scoped set (out + delivered == total)

Runs against the live Postgres test DB: seed rows with a unique order_number
prefix, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterator

import pytest
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.order import Customer, Order, OrderStatus
from app.services.order_service import OrderService

PREFIX = "OOUT-"
CUSTOMER_NAME = "OOUT TEST CUSTOMER SDN BHD"


def _cleanup() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM orders WHERE order_number LIKE 'OOUT-%'"))
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


def _status_id(db: Session, code: str) -> str:
    row = (
        db.query(OrderStatus.id)
        .filter(func.lower(OrderStatus.status_code) == code.lower())
        .first()
    )
    assert row, f"test DB needs an order_statuses row with status_code={code!r}"
    return str(row.id)


def _seed(db: Session):
    """One customer + five orders spanning the delivered/outstanding boundary.

    delivered   : DELIVERED+date, COMPLETED+date
    outstanding : NEW (no date), NEW+date (the Status/date inconsistency), CANCELLED
    """
    cust = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"{PREFIX}C1",
        customer_name=CUSTOMER_NAME,
    )
    db.add(cust)
    db.flush()

    delivered = _status_id(db, "delivered")
    completed = _status_id(db, "completed")
    new = _status_id(db, "new")
    cancelled = _status_id(db, "cancelled")

    def mk(num, status_id, add):
        return Order(
            id=str(uuid.uuid4()),
            order_number=f"{PREFIX}{num}",
            customer_id=cust.id,
            debtor_name=CUSTOMER_NAME,
            order_date=datetime(2026, 1, 1),
            order_status_id=status_id,
            actual_delivery_date=add,
        )

    orders = {
        "delivered": mk("0001", delivered, datetime(2026, 1, 3)),
        "completed": mk("0002", completed, datetime(2026, 1, 4)),
        "new_no_date": mk("0003", new, None),
        "new_with_date": mk("0004", new, datetime(2026, 1, 5)),  # inconsistency
        "cancelled": mk("0005", cancelled, None),
    }
    db.add_all(list(orders.values()))
    db.commit()
    return cust, orders


def _numbers(rows) -> set[str]:
    return {r.order_number for r in rows["data"]}


def _list(db, cust, **kw) -> set[str]:
    res = OrderService(db).list_orders(
        customer_ids=[str(cust.id)], limit=100, **kw
    )
    return _numbers(res)


def test_delivered_returns_only_delivered(db: Session) -> None:
    cust, _ = _seed(db)
    got = _list(db, cust, order_status="delivered")
    assert got == {f"{PREFIX}0001", f"{PREFIX}0002"}


def test_outstanding_returns_only_not_delivered(db: Session) -> None:
    cust, _ = _seed(db)
    got = _list(db, cust, order_status="outstanding")
    # NEW (no date), NEW+date (inconsistency), CANCELLED
    assert got == {f"{PREFIX}0003", f"{PREFIX}0004", f"{PREFIX}0005"}


def test_new_order_with_delivery_date_is_outstanding(db: Session) -> None:
    """The flagged case: a non-delivered status with a stray delivery date must
    read as outstanding, never delivered."""
    cust, _ = _seed(db)
    assert f"{PREFIX}0004" in _list(db, cust, order_status="outstanding")
    assert f"{PREFIX}0004" not in _list(db, cust, order_status="delivered")


def test_null_and_unknown_bucket_no_filter(db: Session) -> None:
    cust, _ = _seed(db)
    all_five = {f"{PREFIX}000{i}" for i in range(1, 6)}
    assert _list(db, cust) == all_five  # omitted
    assert _list(db, cust, order_status=None) == all_five
    assert _list(db, cust, order_status="") == all_five
    assert _list(db, cust, order_status="not-a-bucket") == all_five


def test_buckets_partition_the_scope(db: Session) -> None:
    cust, _ = _seed(db)
    out = _list(db, cust, order_status="outstanding")
    dlv = _list(db, cust, order_status="delivered")
    assert out.isdisjoint(dlv)
    assert out | dlv == _list(db, cust)
