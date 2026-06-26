"""Service + endpoint tests for the orders record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for delivery orders. Covers the
acceptance criteria in docs/plans/PLAN-record-navigation-standardization.md §9:

- filtered total equals the filtered count, NOT the unfiltered total
- 1-based index within the filtered + sorted set
- prev/next are the correct adjacent records
- active sort direction reorders the neighbours
- circular wrap (first.prev = last, last.next = first)
- out-of-filter record -> D2 fallback to the unfiltered set
- /neighbours endpoint enforces auth -> 401/403 with no principal
- no filter -> behaves over the full set

Runs against the live Postgres test DB (same pattern as the other order
tests): seed rows with a unique order_number prefix, assert, clean up.

The neighbours query reuses ``OrderService.list_orders(ids_only=True)`` — the
exact same filter+sort query object the paginated grid builds — so list and
neighbours can never drift.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.order import Order
from app.services.order_service import OrderService

# Unique marker so the filter `query=` matches ONLY this test's rows (the list
# `query` searches order_number among other columns) — keeps the filtered-count
# assertions exact even on the shared DB.
PREFIX = "ONBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM orders WHERE order_number LIKE 'ONBR-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM orders WHERE order_number LIKE 'ONBR-%'"))
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(
    db: Session,
    order_number: str,
    *,
    debtor_name: str = "ACME",
) -> Order:
    o = Order(
        id=str(uuid.uuid4()),
        order_number=order_number,
        debtor_name=debtor_name,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _seed_ordered_set(db: Session, n: int = 5) -> list[Order]:
    """Seed n orders whose debtor_name sorts deterministically D0..Dn-1.

    Sorting asc by debtor_name yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    rows: list[Order] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                order_number=f"{PREFIX}{i}",
                debtor_name=f"ONBRCUST-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: OrderService.order_neighbours                                  #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = OrderService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by debtor_name asc.
    out = svc.order_neighbours(
        rows[2].id, query=PREFIX, sort_field="debtor_name", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug. Seed a filtered subset plus extra non-matching rows; the
    # neighbours total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # order_number ONBR-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, order_number=f"ONBR-NOISE-{i}", debtor_name=f"ZZZ-{i}")

    svc = OrderService(db)
    unfiltered = svc.order_neighbours(target[0].id)  # no query -> whole set
    filtered = svc.order_neighbours(target[0].id, query=PREFIX, sort_field="debtor_name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # Flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # debtor_name ONBRCUST-000..004
    svc = OrderService(db)
    asc = svc.order_neighbours(rows[2].id, query=PREFIX, sort_field="debtor_name", sort_dir="asc")
    desc = svc.order_neighbours(rows[2].id, query=PREFIX, sort_field="debtor_name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = OrderService(db)
    out = svc.order_neighbours(rows[0].id, query=PREFIX, sort_field="debtor_name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = OrderService(db)
    out = svc.order_neighbours(rows[3].id, query=PREFIX, sort_field="debtor_name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead, and the total
    # reflects the unfiltered count (D2).
    _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, order_number="ONBR-OUTSIDE-1", debtor_name="ZZZ-out")

    svc = OrderService(db)
    # Compute the true unfiltered total to compare against.
    unfiltered_total = svc.order_neighbours(outside.id)["total"]

    out = svc.order_neighbours(outside.id, query=PREFIX, sort_field="debtor_name")
    # Fell back: index resolved against the unfiltered set, total == unfiltered.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_accepts_order_number_identifier(db: Session) -> None:
    # The endpoint accepts a UUID or an order_number; an order_number must resolve
    # to the same neighbours as the canonical UUID.
    rows = _seed_ordered_set(db, 4)
    svc = OrderService(db)
    by_uuid = svc.order_neighbours(rows[1].id, query=PREFIX, sort_field="debtor_name")
    by_number = svc.order_neighbours(rows[1].order_number, query=PREFIX, sort_field="debtor_name")
    assert by_number["index"] == by_uuid["index"]
    assert by_number["prev_id"] == by_uuid["prev_id"]
    assert by_number["next_id"] == by_uuid["next_id"]


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at
    # least the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = OrderService(db)
    out = svc.order_neighbours(rows[1].id, sort_field="debtor_name", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

def test_neighbours_endpoint_requires_auth() -> None:
    # No Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/order-management/orders/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422, or auth rejection;
    # assert it is NOT a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/order-management/orders/neighbours")
    assert res.status_code in (401, 403, 422), res.text
