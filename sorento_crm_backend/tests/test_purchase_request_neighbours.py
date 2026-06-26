"""Service + endpoint tests for the purchase-request / sponsorship-form
record-navigation feature.

Mirrors tests/test_complaint_neighbours.py and tests/test_stock_inquiry_neighbours.py
for the PR/SF resource (one shared model, discriminated by ``request_type``):

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort (column + dir) reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- request_type is respected -> PR navigation stays within PRs and SF within SFs.
- out-of-filter record -> D2 fallback (still scoped to request_type) so the pager
  is never dead.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- no filter -> behaves over the full set.

Runs against the live Postgres test DB: seed rows with a unique request_number
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
from app.models.procurement import PurchaseRequestHeader
from app.services.procurement_service import PurchaseRequestService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "PRNBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM purchase_requests WHERE request_number LIKE 'PRNBR-%'")
            )
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM purchase_requests WHERE request_number LIKE 'PRNBR-%'")
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
    request_number: str,
    *,
    request_type: str = "purchase_request",
    customer_name: str | None = None,
    approval_status: str | None = None,
) -> PurchaseRequestHeader:
    h = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number=request_number,
        customer_name=customer_name,
        approval_status=approval_status,
        status="draft",
        source="external",
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _seed_ordered_set(
    db: Session, n: int = 5, *, request_type: str = "purchase_request"
) -> list[PurchaseRequestHeader]:
    """Seed n requests whose customer_name sorts deterministically C0..Cn-1.

    Sorting asc by customer_name yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    rows: list[PurchaseRequestHeader] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                request_number=f"{PREFIX}{i:03d}",
                request_type=request_type,
                customer_name=f"PRNBRCUST-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: PurchaseRequestService.neighbours                              #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = PurchaseRequestService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by customer_name asc.
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug. Seed a filtered subset plus extra non-matching rows; the neighbours
    # total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # request_number PRNBR-04-000..002
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, request_number=f"PRNBR-NOISE-{i}", customer_name=f"ZZZ-{i}")

    svc = PurchaseRequestService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="customer_name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # Flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # customer_name PRNBRCUST-000..004
    svc = PurchaseRequestService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = PurchaseRequestService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = PurchaseRequestService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_request_type_respected_pr_stays_in_pr(db: Session) -> None:
    # Resource-specific: the list filter includes request_type, so PR navigation
    # must stay within PRs and never include sponsorship forms (and vice-versa).
    prs = _seed_ordered_set(db, 3, request_type="purchase_request")
    # Sponsorship forms that match query=PREFIX/customer_name but are a different type.
    for i in range(4):
        _seed(
            db,
            request_number=f"{PREFIX}SF-{i}",
            request_type="sponsorship_form",
            customer_name=f"PRNBRCUST-9{i:02d}",
        )

    svc = PurchaseRequestService(db)
    out = svc.neighbours(
        prs[0].id,
        query=PREFIX,
        request_type="purchase_request",
        sort_field="customer_name",
        sort_dir="asc",
    )
    # Only the 3 PRs are in scope despite the 4 matching SFs.
    assert out["total"] == 3
    pr_ids = {r.id for r in prs}
    assert out["prev_id"] in pr_ids and out["next_id"] in pr_ids


def test_neighbours_out_of_filter_falls_back_scoped_to_request_type(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must fall
    # back to the default-sorted set (still scoped to request_type) so the pager is
    # never dead, and the total reflects the request_type-scoped count.
    _seed_ordered_set(db, 3)  # match query=PREFIX (purchase_request)
    # A PR that does NOT match query=PREFIX.
    outside = _seed(db, request_number="PRNBR-OUTSIDE-1", customer_name="ZZZ-out")
    # A sponsorship form that must NOT be counted on the PR fallback.
    _seed(
        db,
        request_number="PRNBR-OUTSIDE-SF",
        request_type="sponsorship_form",
        customer_name="ZZZ-sf",
    )

    svc = PurchaseRequestService(db)
    # True PR-only unfiltered total to compare against.
    pr_only_total = svc.neighbours(outside.id, request_type="purchase_request")["total"]

    out = svc.neighbours(
        outside.id,
        query=PREFIX,
        request_type="purchase_request",
        sort_field="customer_name",
    )
    # Fell back: index resolved, total == the PR-only count (never wraps into SFs).
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == pr_only_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at least
    # the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = PurchaseRequestService(db)
    out = svc.neighbours(rows[1].id, sort_field="customer_name", sort_dir="asc")
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
            "/api/v1/procurement/purchase-requests/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422 (or auth rejection), never
    # a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/procurement/purchase-requests/neighbours")
    assert res.status_code in (401, 403, 422), res.text
