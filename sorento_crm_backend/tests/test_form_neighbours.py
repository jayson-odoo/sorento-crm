"""Service + endpoint tests for the forms (definitions) record-navigation feature.

Mirrors tests/test_complaint_neighbours.py and the acceptance criteria in
docs/plans/PLAN-record-navigation-standardization.md §9:

- UAC-1 / UAC-5  filtered total equals the filtered count, NOT the unfiltered total.
- UAC-2          1-based index within the filtered + sorted set.
- UAC-3          prev/next are the correct adjacent records.
- UAC-4          active sort (column + dir) reorders the neighbours.
- UAC-6          circular wrap (first.prev = last, last.next = first).
- UAC-8          out-of-filter record -> D2 fallback to the unfiltered set; total
                 equals the unfiltered count.
- UAC-11         /neighbours endpoint enforces auth -> 401/403 with no principal.
- UAC-13         no filter -> behaves over the full set.

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
from app.models.forms import Form
from app.services.forms_service import FormService

# Unique marker so the filter `query=` matches ONLY this test's rows and nothing
# else already in the shared DB (keeps the filtered-count assertions exact).
PREFIX = "NBRFORM-04-"


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM forms WHERE code LIKE 'NBRFORM-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM forms WHERE code LIKE 'NBRFORM-%'"))
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
    code: str,
    *,
    name: str = "Form",
    form_type: str = "marketing",
    language: str = "en",
    is_active: bool = True,
) -> Form:
    f = Form(
        id=str(uuid.uuid4()),
        code=code,
        name=name,
        form_type=form_type,
        language=language,
        is_active=is_active,
        access_levels=["dealer", "end_user"],
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _seed_ordered_set(db: Session, n: int = 5) -> list[Form]:
    """Seed n forms whose name sorts deterministically N0..Nn-1.

    Sorting asc by name yields exactly this order, so neighbour expectations
    are unambiguous.
    """
    rows: list[Form] = []
    for i in range(n):
        rows.append(
            _seed(
                db,
                code=f"{PREFIX}{i}",
                name=f"NBRFORMNAME-{i:03d}",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Service-level: FormService.neighbours                                         #
# --------------------------------------------------------------------------- #

def test_neighbours_middle_record_happy_path(db: Session) -> None:
    rows = _seed_ordered_set(db, 5)
    svc = FormService(db)
    # query=PREFIX restricts to exactly our 5 rows; sort by name asc.
    out = svc.neighbours(rows[2].id, query=PREFIX, sort_field="name", sort_dir="asc")
    assert out["total"] == 5
    assert out["index"] == 3  # UAC-2: 1-based position of the 3rd row
    assert out["prev_id"] == rows[1].id  # UAC-3
    assert out["next_id"] == rows[3].id


def test_neighbours_filter_respected_total_equals_filtered_count(db: Session) -> None:
    # UAC-1 / UAC-5: the bug. Seed a filtered subset plus extra non-matching rows;
    # the neighbours total must equal the filtered count, not the unfiltered total.
    target = _seed_ordered_set(db, 3)  # code NBRFORM-04-0..2
    # Noise: rows that do NOT match query=PREFIX (different code prefix).
    for i in range(4):
        _seed(db, code=f"NBRFORM-NOISE-{i}", name=f"ZZZ-{i}")

    svc = FormService(db)
    unfiltered = svc.neighbours(target[0].id)  # no query -> whole set
    filtered = svc.neighbours(target[0].id, query=PREFIX, sort_field="name")

    assert filtered["total"] == 3, "filtered total must equal the filtered count (UAC-1)"
    # The whole bug: filtered total must NOT equal the unfiltered total.
    assert filtered["total"] != unfiltered["total"]
    # Neighbours stay within the filtered set.
    filtered_ids = {r.id for r in target}
    assert filtered["prev_id"] in filtered_ids
    assert filtered["next_id"] in filtered_ids


def test_neighbours_sort_dir_reorders_neighbours(db: Session) -> None:
    # UAC-4: flipping the sort direction swaps prev/next.
    rows = _seed_ordered_set(db, 5)  # name NBRFORMNAME-000..004
    svc = FormService(db)
    asc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="name", sort_dir="asc")
    desc = svc.neighbours(rows[2].id, query=PREFIX, sort_field="name", sort_dir="desc")
    # asc: ...001, 002, 003...  desc: ...003, 002, 001...
    assert asc["prev_id"] == rows[1].id and asc["next_id"] == rows[3].id
    assert desc["prev_id"] == rows[3].id and desc["next_id"] == rows[1].id
    assert asc["total"] == desc["total"] == 5


def test_neighbours_first_record_prev_wraps_to_last(db: Session) -> None:
    # UAC-6: circular wrap on the first record.
    rows = _seed_ordered_set(db, 4)
    svc = FormService(db)
    out = svc.neighbours(rows[0].id, query=PREFIX, sort_field="name", sort_dir="asc")
    assert out["index"] == 1
    assert out["prev_id"] == rows[3].id  # wraps to last
    assert out["next_id"] == rows[1].id


def test_neighbours_last_record_next_wraps_to_first(db: Session) -> None:
    rows = _seed_ordered_set(db, 4)
    svc = FormService(db)
    out = svc.neighbours(rows[3].id, query=PREFIX, sort_field="name", sort_dir="asc")
    assert out["index"] == 4
    assert out["next_id"] == rows[0].id  # wraps to first
    assert out["prev_id"] == rows[2].id


def test_neighbours_out_of_filter_falls_back_to_unfiltered(db: Session) -> None:
    # UAC-8: the record exists but is NOT in the active filtered set. The service
    # must fall back to the unfiltered set so the pager is never dead, and the
    # total reflects the unfiltered count, not the filtered one.
    #
    # This used to prove that second half by comparing two SEPARATELY fetched
    # live totals of the real, shared `forms` table for equality (one probe
    # call, then `out["total"]` from the fallback). Another xdist worker's
    # file can insert/delete rows in the gap between them (BL-034's exact
    # shape, first found on `tests/test_complaint_neighbours.py`). What
    # matters - that the fallback used the unfiltered scope, not the filtered
    # one - is provable from this test's own marker rows alone.
    in_set = _seed_ordered_set(db, 3)  # match query=PREFIX
    # A row that does NOT match query=PREFIX.
    outside = _seed(db, code="NBRFORM-OUTSIDE-1", name="ZZZ-out")
    own_ids = {r.id for r in in_set} | {outside.id}

    svc = FormService(db)
    out = svc.neighbours(outside.id, query=PREFIX, sort_field="name")
    # Fell back: not found in the filtered 3-row set, so index resolved against
    # the wider one instead of staying None.
    assert out["index"] is not None, "D2 fallback must resolve the record"
    assert out["total"] > 3  # bigger than the filtered subset

    fallback_ids = {
        str(row[0])
        for row in svc._build_list_query(with_options=False).with_entities(Form.id).all()
    }
    assert own_ids <= fallback_ids


def test_neighbours_no_filter_uses_full_set(db: Session) -> None:
    # UAC-13: no active filter -> neighbours computed over the full set; total is
    # at least the number we seeded (other rows may exist in the shared DB).
    rows = _seed_ordered_set(db, 3)
    svc = FormService(db)
    out = svc.neighbours(rows[1].id, sort_field="name", sort_dir="asc")
    assert out["index"] is not None
    assert out["total"] >= 3
    assert out["prev_id"] is not None and out["next_id"] is not None


def test_neighbours_status_filter_respected(db: Session) -> None:
    # Active/inactive split: status='active' restricts the set to active forms only.
    active_rows = []
    for i in range(3):
        active_rows.append(
            _seed(db, code=f"{PREFIX}A{i}", name=f"NBRACTIVE-{i:03d}", is_active=True)
        )
    for i in range(2):
        _seed(db, code=f"{PREFIX}I{i}", name=f"NBRINACTIVE-{i:03d}", is_active=False)

    svc = FormService(db)
    out = svc.neighbours(
        active_rows[1].id, query=PREFIX, status="active", sort_field="name", sort_dir="asc"
    )
    assert out["total"] == 3  # inactive rows excluded
    active_ids = {r.id for r in active_rows}
    assert out["prev_id"] in active_ids
    assert out["next_id"] in active_ids


# --------------------------------------------------------------------------- #
# Endpoint-level                                                                #
# --------------------------------------------------------------------------- #

def test_neighbours_endpoint_requires_auth() -> None:
    # UAC-11: no Bearer token, no X-API-Key -> 401/403.
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/forms-management/forms/neighbours",
            params={"id": str(uuid.uuid4())},
        )
    assert res.status_code in (401, 403), res.text


def test_neighbours_endpoint_missing_id_is_422_or_auth() -> None:
    # Contract: id is required -> FastAPI validation 422 (or auth rejection). Assert
    # it is NOT a 200/500.
    with TestClient(app) as client:
        res = client.get("/api/v1/forms-management/forms/neighbours")
    assert res.status_code in (401, 403, 422), res.text
