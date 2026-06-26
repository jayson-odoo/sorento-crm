"""Service + endpoint tests for the suppliers record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for the suppliers resource, covering
the locked decisions in docs/plans/PLAN-record-navigation-standardization.md:

- Filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- Active sort direction reorders the neighbours.
- Circular wrap (first.prev = last, last.next = first).
- Out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- No filter -> behaves over the full set.

Runs against the live Postgres test DB (same pattern as the complaint
neighbours tests): seed rows with a unique supplier_code prefix, assert,
clean up.
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
from app.models.procurement import Supplier
from app.services.procurement_service import SupplierService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact). The
# supplier list search matches supplier_code and supplier_name, so we anchor both
# on the prefix.
PREFIX = "SUPNBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM suppliers WHERE supplier_code LIKE 'SUPNBR-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM suppliers WHERE supplier_code LIKE 'SUPNBR-%'"))
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
    supplier_code: str,
    *,
    supplier_name: str = "ACME",
) -> Supplier:
    s = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=supplier_code,
        supplier_name=supplier_name,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_ordered_set(db: Session, n: int = 5) -> list[Supplier]:
    """Seed n suppliers whose supplier_name sorts deterministically S0..Sn-1.

    Sorting asc by supplier_name yields exactly this order, so neighbour
    expectations are unambiguous. supplier_code carries the PREFIX so query=
    matches exactly this set.
    """
    rows: list[Supplier] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                supplier_code=f"{PREFIX}{i}",
                supplier_name=f"SUPNBR-NAME-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: SupplierService.neighbours                                     #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = SupplierService(db)
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="supplier_name", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # Seed a filtered subset plus extra non-matching rows; the neighbours total
    # must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # supplier_code SUPNBR-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, supplier_code=f"SUPNBR-NOISE-{i}", supplier_name=f"ZZZ-{i}")

    svc = SupplierService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="supplier_name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # Flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # supplier_name SUPNBR-NAME-000..004
    svc = SupplierService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="supplier_name", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="supplier_name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = SupplierService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="supplier_name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = SupplierService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="supplier_name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead, and the total
    # reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, supplier_code="SUPNBR-OUTSIDE-1", supplier_name="ZZZ-out")

    svc = SupplierService(db)
    # Compute the true unfiltered total to compare against.
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort_field="supplier_name")
    # Fell back: index resolved against the unfiltered set, total == unfiltered.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at least
    # the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = SupplierService(db)
    out = svc.neighbours(rows[1].id, sort_field="supplier_name", sort_dir="asc")
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
            "/api/v1/procurement/suppliers/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422 (or auth rejection before
    # validation). Assert it is NOT a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/procurement/suppliers/neighbours")
    assert res.status_code in (401, 403, 422), res.text
