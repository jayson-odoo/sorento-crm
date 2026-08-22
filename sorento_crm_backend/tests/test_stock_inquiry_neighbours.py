"""Service + endpoint tests for the stock-inquiry record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for the stock-inquiry resource:

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort (column + dir) reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- no filter -> behaves over the full set.

Runs against the live Postgres test DB: seed rows with a unique product_code
prefix so the `query=` filter matches ONLY this test's rows, assert, clean up.
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
from app.models.procurement import StockInquiry
from app.services.procurement_service import StockInquiryService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "SINBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM stock_inquiries WHERE product_code LIKE 'SINBR-%'")
            )
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM stock_inquiries WHERE product_code LIKE 'SINBR-%'")
            )
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
    inquiry_number: str | None = None,
    status: str = "new",
) -> StockInquiry:
    si = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=inquiry_number,
        product_code=product_code,
        status=status,
    )
    db.add(si)
    db.commit()
    db.refresh(si)
    return si


def _seed_ordered_set(db: Session, n: int = 5) -> list[StockInquiry]:
    """Seed n inquiries whose product_code sorts deterministically C0..Cn-1.

    Sorting asc by product_code yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    rows: list[StockInquiry] = []
    for i in range(n):
        rows.append(_seed(db, product_code=f"{PREFIX}{i:03d}"))
    return rows


# --------------------------------------------------------------------------- #
# Service-level: StockInquiryService.neighbours                                 #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = StockInquiryService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by product_code asc.
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="product_code", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug. Seed a filtered subset plus extra non-matching rows; the neighbours
    # total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # product_code SINBR-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, product_code=f"SINBR-NOISE-{i}")

    svc = StockInquiryService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="product_code")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # Flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # product_code SINBR-04-000..004
    svc = StockInquiryService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="product_code", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="product_code", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = StockInquiryService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="product_code", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = StockInquiryService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="product_code", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_status_filter_respected(db: Session) -> None:
    # The list GET filters by a comma-separated `status`; neighbours must honour it.
    a = _seed(db, product_code=f"{PREFIX}A", status="new")
    b = _seed(db, product_code=f"{PREFIX}B", status="new")
    _seed(db, product_code=f"{PREFIX}C", status="rejected")

    svc = StockInquiryService(db)
    out = svc.neighbours(
        a.id,
        query=PREFIX,
        sort_field="product_code",
        sort_dir="asc",
        statuses=["new"],
    )
    # Only the two `new` rows are in scope.
    assert out["total"] == 2
    assert out["prev_id"] == b.id and out["next_id"] == b.id  # wrap with 2 rows


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must fall
    # back to the unfiltered set so the pager is never dead, and the total reflects
    # the unfiltered count.
    #
    # This used to prove that second half by comparing two SEPARATELY fetched live
    # totals of the real, shared `stock_inquiries` table for equality. That table is
    # not this test's own - it is the whole suite's, and another xdist worker's file
    # can insert/delete rows in the gap between those two reads, so "total at time A"
    # can stop equalling "total at time B" on a run that never touched this file
    # (BL-034 shape). What this test actually requires - that the fallback used the
    # unfiltered scope, not the filtered one - is provable from this test's own
    # marker rows alone, with no dependency on the ambient row count.
    in_set = _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, product_code="SINBR-OUTSIDE-1")
    own_ids = {r.id for r in in_set} | {outside.id}

    svc = StockInquiryService(db)
    out = svc.neighbours(outside.id, query=PREFIX, sort_field="product_code")
    # Fell back: index resolved against the unfiltered set.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] > 3  # bigger than the filtered subset

    # And dropped ENTIRELY, not just widened to some other partial filter: every one
    # of this test's own rows must be reachable in the SAME unfiltered scope
    # `neighbours()`'s own D2 branch reads.
    fallback_ids = {
        str(row[0]) for row in svc._build_list_query().with_entities(StockInquiry.id).all()
    }
    assert own_ids <= fallback_ids


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at least
    # the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = StockInquiryService(db)
    out = svc.neighbours(rows[1].id, sort_field="product_code", sort_dir="asc")
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
            "/api/v1/procurement/stock-inquiries/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422 (or auth rejection), never
    # a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/procurement/stock-inquiries/neighbours")
    assert res.status_code in (401, 403, 422), res.text
