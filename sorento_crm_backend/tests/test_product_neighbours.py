"""Service + endpoint tests for the products record-navigation feature.

Mirrors tests/test_complaint_neighbours.py / tests/test_supplier_neighbours.py for
the products resource, covering the locked decisions in
docs/plans/PLAN-record-navigation-standardization.md:

- Filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- Active sort direction reorders the neighbours.
- Circular wrap (first.prev = last, last.next = first).
- Out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- No filter -> behaves over the full set.

Runs against the live Postgres test DB (same pattern as the supplier/complaint
neighbours tests): seed rows with a unique product_code prefix, assert, clean up.
The product list search matches product_code / product_name / description, so we
anchor product_code on the prefix and order by product_name.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_service import ProductService


def _fk_ids(db: Session) -> tuple[str, str]:
    """Resolve an existing category + base UoM (both NOT NULL on products) from the
    shared dev DB, so seeded products satisfy the FK constraints."""
    cat = db.query(ProductCategory.id).first()
    uom = db.query(UnitOfMeasure.id).first()
    assert cat and uom, "dev DB must have at least one product_category + unit_of_measure"
    return str(cat[0]), str(uom[0])

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "PRDNBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM products WHERE product_code LIKE 'PRDNBR-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM products WHERE product_code LIKE 'PRDNBR-%'"))
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
    product_code: str,
    *,
    product_name: str = "ACME",
    is_active: bool = True,
) -> Product:
    category_id, base_uom_id = _fk_ids(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=product_code,
        product_name=product_name,
        category_id=category_id,
        base_uom_id=base_uom_id,
        list_price=Decimal("0"),
        is_active=is_active,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed_ordered_set(db: Session, n: int = 5) -> list[Product]:
    """Seed n products whose product_name sorts deterministically P0..Pn-1.

    Sorting asc by product_name yields exactly this order, so neighbour
    expectations are unambiguous. product_code carries the PREFIX so query=
    matches exactly this set.
    """
    rows: list[Product] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                product_code=f"{PREFIX}{i}",
                product_name=f"PRDNBR-NAME-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: ProductService.neighbours                                      #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = ProductService(db)
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="product_name", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # Seed a filtered subset plus extra non-matching rows; the neighbours total
    # must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # product_code PRDNBR-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, product_code=f"PRDNBR-NOISE-{i}", product_name=f"ZZZ-{i}")

    svc = ProductService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="product_name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # Flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # product_name PRDNBR-NAME-000..004
    svc = ProductService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="product_name", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="product_name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = ProductService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="product_name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = ProductService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="product_name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_status_filter_respected(db: Session) -> None:
    # A bespoke product filter (status=active) must narrow the set the same way
    # the list GET does. Two active + one inactive row; status=active -> total 2.
    a0 = _seed(db, product_code=f"{PREFIX}A0", product_name="PRDNBR-ACT-0", is_active=True)
    a1 = _seed(db, product_code=f"{PREFIX}A1", product_name="PRDNBR-ACT-1", is_active=True)
    _seed(db, product_code=f"{PREFIX}I0", product_name="PRDNBR-INACT-0", is_active=False)

    svc = ProductService(db)
    out = svc.neighbours(
        a0.id, query=PREFIX, status="active", sort_field="product_name", sort_dir="asc"
    )
    assert out["total"] == 2
    assert out["index"] == 1
    # Only the two active rows participate; circular wrap between them.
    assert out["prev_id"] == a1.id
    assert out["next_id"] == a1.id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead, and the total
    # reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, product_code="PRDNBR-OUTSIDE-1", product_name="ZZZ-out")

    svc = ProductService(db)
    # Compute the true unfiltered total to compare against.
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort_field="product_name")
    # Fell back: index resolved against the unfiltered set, total == unfiltered.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_accepts_sku(db: Session) -> None:
    # The detail page may navigate by SKU (product_code); neighbours must resolve
    # it to the canonical UUID so the position math matches the list ids.
    rows = _seed_ordered_set(db, 4)
    svc = ProductService(db)
    out = svc.neighbours(
        rows[1].product_code, query=PREFIX, sort_field="product_name", sort_dir="asc"
    )
    assert out["index"] == 2
    assert out["prev_id"] == rows[0].id
    assert out["next_id"] == rows[2].id


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at least
    # the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = ProductService(db)
    out = svc.neighbours(rows[1].id, sort_field="product_name", sort_dir="asc")
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
            "/api/v1/master-data/products/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422 (or auth rejection before
    # validation). Assert it is NOT a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/master-data/products/neighbours")
    assert res.status_code in (401, 403, 422), res.text
