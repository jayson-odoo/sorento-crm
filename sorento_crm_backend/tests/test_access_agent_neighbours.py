"""Service + endpoint tests for the access-agents record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for the access_agents resource. The
access-agents list GET accepts only a free-text ``query`` (no sort/dir/filters);
the backend always orders by ``code`` (with ``id`` as a deterministic tie-breaker),
so neighbour expectations are unambiguous.

Covers:
- happy path: 1-based index + correct adjacent prev/next within the filtered set.
- filter respected: filtered total equals the filtered count, NOT the unfiltered
  total (the "X / wrong-total" bug).
- circular wrap (first.prev = last, last.next = first).
- D2 fallback: an out-of-filter record resolves against the unfiltered set; total
  equals the unfiltered count.
- no filter -> behaves over the full set.
- /neighbours endpoint enforces auth -> 401/403 with no principal.

Runs against the live Postgres test DB (same pattern as the other tests): seed
rows with a unique code prefix, assert, clean up.
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
from app.models.access import AccessAgent
from app.services.user_service import AccessAgentService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "NBRAGENT-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM access_agents WHERE code LIKE 'NBRAGENT-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM access_agents WHERE code LIKE 'NBRAGENT-%'"))
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


def _seed(db: Session, code: str, *, name: str | None = None) -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()),
        code=code,
        name=name or code,
        is_active=True,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _seed_ordered_set(db: Session, n: int = 5) -> list[AccessAgent]:
    """Seed n agents whose code sorts deterministically C0..Cn-1.

    The backend orders by code asc, so neighbour expectations are unambiguous.
    """
    return [_seed(db, code=f"{PREFIX}{i:03d}") for i in range(n)]


# --------------------------------------------------------------------------- #
# Service-level: AccessAgentService.neighbours                                  #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = AccessAgentService(db)
    out = svc.neighbours(rows[2].id, query=PREFIX)
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug: filtered total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # code NBRAGENT-04-000..002
    # Noise: rows that do NOT match query=PREFIX (different prefix).
    for i in range(4):
        _seed(db, code=f"NBRAGENT-NOISE-{i}")

    svc = AccessAgentService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX)

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # Circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = AccessAgentService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX)
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = AccessAgentService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX)
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead, and the total
    # reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=PREFIX
    outside = _seed(db, code="NBRAGENT-OUTSIDE-1")  # does NOT match query=PREFIX

    svc = AccessAgentService(db)
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX)
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # No active filter -> neighbours computed over the full set; total is at least
    # the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = AccessAgentService(db)
    out = svc.neighbours(rows[1].id)
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
            "/api/v1/user-management/access-agents/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    # Contract: id is required -> assert it is NOT a 200/500 (auth rejection or 422).
    with TestClient(app) as client:
        res = client.get("/api/v1/user-management/access-agents/neighbours")
    assert res.status_code in (401, 403, 422), res.text
