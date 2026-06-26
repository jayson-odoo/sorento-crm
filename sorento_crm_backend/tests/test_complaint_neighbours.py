"""Service + endpoint tests for the complaints record-navigation feature.

Covers the acceptance criteria in
docs/plans/PLAN-record-navigation-standardization.md §9:

- UAC-1 / UAC-5  filtered total equals the filtered count, NOT the unfiltered total
                 (the original "6 / 44 instead of /23" bug).
- UAC-2          1-based index within the filtered + sorted set.
- UAC-3          prev/next are the correct adjacent records.
- UAC-4          active sort (column + dir) reorders the neighbours.
- UAC-6          circular wrap (first.prev = last, last.next = first).
- UAC-8          out-of-filter record -> D2 fallback to the unfiltered set; total
                 equals the unfiltered count.
- UAC-11         /neighbours endpoint enforces auth -> 401/403 with no principal.
- UAC-13         no filter -> behaves over the full set.

Runs against the live Postgres test DB (same pattern as the other complaint
tests): seed rows with a unique complaint_number prefix, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.complaints import Complaint
from app.services.complaints_service import ComplaintService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "NBR-04-"
ASSIGNEE = "nbr-assignee-1"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'NBR-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'NBR-%'"))
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
    complaint_number: str,
    *,
    customer_name: str = "ACME",
    status: str = "new",
    assigned_to=None,
    complaint_date=None,
) -> Complaint:
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=complaint_number,
        customer_name=customer_name,
        status=status,
        assigned_to=assigned_to,
        complaint_date=complaint_date,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_ordered_set(db: Session, n: int = 5) -> list[Complaint]:
    """Seed n complaints whose customer_name sorts deterministically C0..Cn-1.

    Sorting asc by customer_name yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    rows: list[Complaint] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                complaint_number=f"{PREFIX}{i}",
                customer_name=f"NBRCUST-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: ComplaintService.neighbours                                    #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = ComplaintService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by customer_name asc.
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # UAC-2: 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id  # UAC-3
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # UAC-1 / UAC-5: THE bug. Seed a filtered subset plus extra non-matching rows;
    # the neighbours total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # complaint_number NBR-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, complaint_number=f"NBR-NOISE-{i}", customer_name=f"ZZZ-{i}")

    svc = ComplaintService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="customer_name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count (UAC-1)"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # UAC-4: flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # customer_name NBRCUST-000..004
    svc = ComplaintService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="customer_name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # UAC-6: circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = ComplaintService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = ComplaintService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="customer_name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # UAC-8: the record exists but is NOT in the active filtered set. The service
    # must fall back to the unfiltered set so the pager is never dead, and the
    # total reflects the unfiltered count.
    in_set = _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, complaint_number="NBR-OUTSIDE-1", customer_name="ZZZ-out")

    svc = ComplaintService(db)
    # Compute the true unfiltered total to compare against.
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort_field="customer_name")
    # Fell back: index resolved against the unfiltered set, total == unfiltered.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # UAC-13: no active filter -> neighbours computed over the full set; total is
    # at least the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = ComplaintService(db)
    out = svc.neighbours(rows[1].id, sort_field="customer_name", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

def test_neighbours_endpoint_requires_auth() -> None:
    # UAC-11: no Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/complaints-management/complaints/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> FastAPI validation 422 (before auth on a missing
    # required query param FastAPI may 422; either 422 or auth rejection is fine,
    # but assert it is NOT a 200/500).
    with TestClient(app) as client:
        res = client.get("/api/v1/complaints-management/complaints/neighbours")
    assert res.status_code in (401, 403, 422), res.text
