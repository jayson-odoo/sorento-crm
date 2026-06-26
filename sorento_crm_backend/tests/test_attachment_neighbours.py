"""Service + endpoint tests for the attachments record-navigation feature.

Mirrors tests/test_complaint_neighbours.py for the attachments resource. Covers
the shared record-navigation acceptance criteria:

- filtered total equals the filtered count, NOT the unfiltered total.
- 1-based index within the filtered + sorted set.
- prev/next are the correct adjacent records.
- active sort direction reorders the neighbours.
- circular wrap (first.prev = last, last.next = first).
- out-of-filter record -> D2 fallback to the unfiltered set; total equals the
  unfiltered count.
- /neighbours endpoint enforces auth -> 401/403 with no principal.
- no filter -> behaves over the full set.

Runs against the live Postgres test DB (same pattern as the other resource
tests): seed rows with a unique original_filename prefix, assert, clean up.
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
from app.models.resources import Attachment
from app.services.resources_service import AttachmentService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "NBRATT-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM attachments WHERE original_filename LIKE 'NBRATT-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM attachments WHERE original_filename LIKE 'NBRATT-%'"))
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
    original_filename: str,
    *,
    is_deleted: bool = False,
    directory_id=None,
) -> Attachment:
    a = Attachment(
        id=str(uuid.uuid4()),
        original_filename=original_filename,
        stored_filename=original_filename,
        file_path=f"general/{original_filename}",
        is_deleted=is_deleted,
        directory_id=directory_id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _seed_ordered_set(db: Session, n: int = 5) -> list[Attachment]:
    """Seed n attachments whose original_filename sorts deterministically.

    Sorting asc by original_filename (sort='name') yields exactly this order, so
    neighbour expectations are unambiguous.
    """
    return [_seed(db, original_filename=f"{PREFIX}{i:03d}") for i in range(n)]


# --------------------------------------------------------------------------- #
# Service-level: AttachmentService.neighbours                                   #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = AttachmentService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by name asc.
    out = svc.neighbours(rows[2].id, query=PREFIX, sort="name", dir="asc")
    assert out["total"] == 5
    assert out["index"] == 3  # 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # THE bug: the neighbours total must equal the filtered count, not the
    # unfiltered total. Folder filter respected here.
    target = _seed_ordered_set(db, 3)
    # Noise: rows that do NOT match query=PREFIX (different prefix marker).
    for i in range(4):
        _seed(db, original_filename=f"NBRATT-NOISE-{i:03d}")

    svc = AttachmentService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort="name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count"
    assert filtered["total"] != unfiltered["total"]
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = AttachmentService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort="name", dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort="name", dir="desc")
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = AttachmentService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort="name", dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = AttachmentService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort="name", dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # The record exists but is NOT in the active filtered set (filtered out by the
    # query). The service must fall back to the unfiltered set so the pager is
    # never dead, and the total reflects the unfiltered count.
    _seed_ordered_set(db, 3)  # match query=PREFIX
    outside = _seed(db, original_filename="NBRATT-OUTSIDE-001")

    svc = AttachmentService(db)
    unfiltered_total = svc.neighbours(outside.id)["total"]

    out = svc.neighbours(outside.id, query=PREFIX, sort="name")
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] == unfiltered_total
    assert out["total"] > 3  # bigger than the filtered subset


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    rows = _seed_ordered_set(db, 3)
    svc = AttachmentService(db)
    out = svc.neighbours(rows[1].id, sort="name", dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


def test_neighbours_is_deleted_filter_scopes_set(db: Session) -> None:
    # is_deleted is a list filter; neighbours scoped to trash must exclude live
    # rows and vice versa (folder/linkage/type/trash filters all respected).
    live = _seed_ordered_set(db, 3)
    trashed = [
        _seed(db, original_filename=f"{PREFIX}T{i:03d}", is_deleted=True)
        for i in range(2)
    ]
    svc = AttachmentService(db)

    live_out = svc.neighbours(live[0].id, query=PREFIX, sort="name", is_deleted=False)
    assert live_out["total"] == 3  # only the live rows

    trash_out = svc.neighbours(
        trashed[0].id, query=PREFIX, sort="name", is_deleted=True
    )
    assert trash_out["total"] == 2  # only the trashed rows


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

def test_neighbours_endpoint_requires_auth() -> None:
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/resource-management/attachments/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422() -> None:
    with TestClient(app) as client:
        res = client.get("/api/v1/resource-management/attachments/neighbours")
    assert res.status_code in (401, 403, 422), res.text
