"""Service + endpoint tests for the GRN (goods received note) record-navigation
feature.

Mirrors tests/test_complaint_neighbours.py and the acceptance criteria in
docs/plans/PLAN-record-navigation-standardization.md §9:

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort direction reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- no filter -> behaves over the full set.

Runs against the live Postgres test DB (same pattern as the other procurement
tests): seed rows with a unique picking_number prefix, assert, clean up. GRNs are
PickingHeader rows with picking_type == 'goods_received'.
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
from app.models.procurement import PickingHeader
from app.services.procurement_service import PickingHeaderService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "GRNNBR-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM picking_headers WHERE picking_number LIKE 'GRNNBR-%'")
            )
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM picking_headers WHERE picking_number LIKE 'GRNNBR-%'")
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
    picking_number: str,
    *,
    picking_status: str = "draft",
    inspection_status: str = "pending",
) -> PickingHeader:
    h = PickingHeader(
        id=str(uuid.uuid4()),
        picking_number=picking_number,
        picking_type="goods_received",
        picking_status=picking_status,
        inspection_status=inspection_status,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _seed_ordered_set(db: Session, n: int = 5) -> list[PickingHeader]:
    """Seed n GRNs whose picking_number sorts deterministically 0..n-1.

    Sorting asc by picking_number yields exactly this order, so neighbour
    expectations are unambiguous.
    """
    rows: list[PickingHeader] = []
    for i in range(n):
        rows.append(_seed(db, picking_number=f"{PREFIX}{i:03d}"))
    return rows


# --------------------------------------------------------------------------- #
# Service-level: PickingHeaderService.neighbours                                #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = PickingHeaderService(db)
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="picking_number", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug: filtered total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # picking_number GRNNBR-04-000..002
    # Noise: rows that do NOT match query=PREFIX (different prefix, still GRN).
    for i in range(4):
        _seed(db, picking_number=f"GRNNBR-NOISE-{i}")

    svc = PickingHeaderService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="picking_number")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)  # picking_number GRNNBR-04-000..004
    svc = PickingHeaderService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="picking_number", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="picking_number", sort_dir="desc")
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = PickingHeaderService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="picking_number", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = PickingHeaderService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="picking_number", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_status_filter_respected(db: Session) -> None:
    # picking_status filter narrows the set; neighbours stay within it.
    approved = [
        _seed(db, picking_number=f"{PREFIX}A{i}", picking_status="approved")
        for i in range(3)
    ]
    # Draft noise that matches the query but not the status filter.
    for i in range(2):
        _seed(db, picking_number=f"{PREFIX}D{i}", picking_status="draft")

    svc = PickingHeaderService(db)
    out = svc.neighbours(
        approved[1].id,
        query=PREFIX,
        picking_status="approved",
        sort_field="picking_number",
        sort_dir="asc",
    )
    assert out["total"] == 3
    approved_ids = {r.id for r in approved}
    assert out["prev_id"] in approved_ids
    assert out["next_id"] in approved_ids


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead (D2), and the
    # total reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=PREFIX
    outside = _seed(db, picking_number="GRNNBR-OUTSIDE-1")  # does NOT match PREFIX

    svc = PickingHeaderService(db)
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort_field="picking_number")
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    rows = _seed_ordered_set(db, 3)
    svc = PickingHeaderService(db)
    out = svc.neighbours(rows[1].id, sort_field="picking_number", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


def test_neighbours_accepts_picking_number_identifier(db: Session) -> None:
    # The endpoint/service resolve a human picking_number to the canonical id.
    rows = _seed_ordered_set(db, 5)
    svc = PickingHeaderService(db)
    out = svc.neighbours(
        rows[2].picking_number,
        query=PREFIX,
        sort_field="picking_number",
        sort_dir="asc",
    )
    assert out["index"] == 3
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

def test_neighbours_endpoint_requires_auth() -> None:
    # No Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/procurement/grn/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422_or_auth() -> None:
    # id is required -> FastAPI 422, or auth rejection first; never a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/procurement/grn/neighbours")
    assert res.status_code in (401, 403, 422), res.text
