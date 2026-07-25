"""Service + endpoint tests for the promotions record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for the promotions resource. Covers
the locked acceptance criteria for the prev/next pager:

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort dir reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- the /neighbours endpoint enforces auth -> 401/403 with no principal.

Uses the same blank-Postgres-schema fixture the other promotion service tests
use (test_promotion_date_mode_filter.py): an empty copy of the real schema, so
no live data interferes and every write is rolled back.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.marketing import Promotion
from app.services.marketing_service import PromotionService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a JSONB->JSON compile shim and a hand-listed
    subset of tables. The real schema has all 199 and the real column types.
    """
    with blank_session() as session:
        yield session


TODAY = datetime.utcnow().date()
# Unique marker so a `query=` filter matches ONLY this test's rows.
PREFIX = "NBRPROMO-"


def _seed(
    db,
    description: str,
    *,
    active: bool = True,
    start_offset: int = -5,
    end_offset: int = 30,
) -> Promotion:
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=TODAY + timedelta(days=start_offset),
        end_date=TODAY + timedelta(days=end_offset),
        is_active=active,
        access_levels=["dealer"],
    )
    db.add(promo)
    db.flush()
    return promo


def _seed_ordered_set(db, n: int = 5) -> list[Promotion]:
    """Seed n active promotions whose description sorts deterministically.

    Sorted by created_at desc is the list default, but we sort the neighbour set
    by query (description) via the search filter; ids are seeded in order so
    start_date asc yields a stable order we can reason about.
    """
    rows: list[Promotion] = []
    for i in range(n):
        # Distinct start_date per row so sort=start_date is unambiguous; the id
        # tie-breaker only matters when these collide.
        rows.append(
            _seed(
                db,
                description=f"{PREFIX}{i:03d}",
                start_offset=-50 + i,  # ascending start_date
                end_offset=30,
            )
        )
    db.commit()
    return rows


# --------------------------------------------------------------------------- #
# Service-level: PromotionService.neighbours                                    #
# --------------------------------------------------------------------------- #


def test_neighbours_middle_record_happy_path(db) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = PromotionService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by start_date asc.
    out = svc.neighbours(
        rows[2].id, query=PREFIX, sort_field="start_date", sort_dir="asc"
    )
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db) -> None:
    # THE bug: neighbours total must equal the filtered count, not the
    # unfiltered total.
    target = _seed_ordered_set(db, 3)  # description NBRPROMO-000..002
    # Noise: rows that do NOT match query=PREFIX.
    for i in range(4):
        _seed(db, description=f"ZZZ-NOISE-{i}")
    db.commit()

    svc = PromotionService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="start_date")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    assert filtered["total"] != unfiltered["total"]
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = PromotionService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="start_date", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="start_date", sort_dir="desc")
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = PromotionService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="start_date", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = PromotionService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="start_date", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_single_record_no_wrap(db) -> None:
    rows = _seed_ordered_set(db, 1)
    svc = PromotionService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="start_date")
    assert out["total"] == 1
    assert out["index"] == 1
    assert out["prev_id"] is None and out["next_id"] is None


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db) -> None:
    # The record exists but is NOT in the active filtered set. The service must
    # fall back to the unfiltered set so the pager is never dead, and the total
    # reflects the unfiltered count (D2).
    in_set = _seed_ordered_set(db, 3)  # match query=PREFIX
    outside = _seed(db, description="ZZZ-OUTSIDE")
    db.commit()

    svc = PromotionService(db)
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort_field="start_date")
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db) -> None:
    rows = _seed_ordered_set(db, 3)
    svc = PromotionService(db)
    out = svc.neighbours(rows[1].id, sort_field="start_date", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


def test_neighbours_inactive_record_resolved_via_active_first_fallback(db) -> None:
    # A promotion whose window has ended is inactive; the active-first fallback
    # (mirrored in neighbours) must still resolve it when narrowed by id.
    expired = _seed(db, description=f"{PREFIX}EXP", start_offset=-40, end_offset=-3)
    db.commit()
    svc = PromotionService(db)
    out = svc.neighbours(expired.id, promotion_ids=[expired.id])
    assert out["index"] == 1
    assert out["total"] == 1


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #


def test_neighbours_endpoint_requires_auth() -> None:
    # No Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/marketing/promotions/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422_or_auth() -> None:
    # id is required -> FastAPI validation 422, or auth rejection first.
    with TestClient(app) as client:
        res = client.get("/api/v1/marketing/promotions/neighbours")
    assert res.status_code in (401, 403, 422), res.text
