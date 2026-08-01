"""Complaint list filtering by root cause / resolution.

Backs the multi-select filters on the Complaints list AND the linked-complaints
grid on a root cause / resolution detail page - both go through
``ComplaintService.list_complaints(root_cause_ids=..., resolution_ids=...)``.

Semantics pinned here: OR within a field, AND across the two fields, and an
EMPTY list means "no filter" rather than "match nothing".
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.complaints.complaints import _csv_ids
from app.database import engine
from tests._pg_fixture import pg_session
from app.models.complaints import Complaint
from app.models.complaint_master_data import ComplaintResolution, ComplaintRootCause
from app.services.company_scope import set_company_scope
from app.services.complaints_service import ComplaintService

_MARK = "RCFILT"


@pytest.fixture(autouse=True)
def _clean_state():
    def _wipe():
        with engine.connect() as conn:
            for sql in (
                f"DELETE FROM complaints WHERE complaint_number LIKE '{_MARK}-%'",
                f"DELETE FROM complaint_root_causes WHERE name LIKE '{_MARK} %'",
                f"DELETE FROM complaint_resolutions WHERE name LIKE '{_MARK} %'",
            ):
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    conn.rollback()

    _wipe()
    yield
    _wipe()


@pytest.fixture
def db() -> Iterator[Session]:
    with pg_session() as s:
        set_company_scope(s, None)
        yield s


def _total(svc: ComplaintService, **kwargs) -> int:
    page = svc.list_complaints(page=1, limit=1, **kwargs)["pagination"]
    return page["total"] if isinstance(page, dict) else page.total


@pytest.fixture
def seeded(db: Session):
    """Two root causes, one resolution, and four complaints across them."""
    rc_a = ComplaintRootCause(id=str(uuid.uuid4()), name=f"{_MARK} Cause A", is_active=True)
    rc_b = ComplaintRootCause(id=str(uuid.uuid4()), name=f"{_MARK} Cause B", is_active=True)
    res = ComplaintResolution(id=str(uuid.uuid4()), name=f"{_MARK} Fix", is_active=True)
    db.add_all([rc_a, rc_b, res])
    db.commit()

    def _complaint(suffix: str, *, root_cause=None, resolution=None, status="approved"):
        c = Complaint(
            id=str(uuid.uuid4()),
            complaint_number=f"{_MARK}-{suffix}",
            status=status,
            root_cause_id=root_cause.id if root_cause is not None else None,
            resolution_id=resolution.id if resolution is not None else None,
        )
        db.add(c)
        return c

    _complaint("A1", root_cause=rc_a)
    _complaint("A2", root_cause=rc_a, resolution=res)
    _complaint("B1", root_cause=rc_b, status="closed")
    _complaint("NONE")
    db.commit()
    return {"rc_a": rc_a, "rc_b": rc_b, "res": res}


def test_single_root_cause_matches_only_its_complaints(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    assert _total(svc, root_cause_ids=[seeded["rc_a"].id]) == 2
    assert _total(svc, root_cause_ids=[seeded["rc_b"].id]) == 1


def test_two_root_causes_are_ored(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    assert _total(svc, root_cause_ids=[seeded["rc_a"].id, seeded["rc_b"].id]) == 3


def test_root_cause_and_resolution_are_anded(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    # A2 is the only complaint with BOTH cause A and the resolution.
    assert (
        _total(svc, root_cause_ids=[seeded["rc_a"].id], resolution_ids=[seeded["res"].id])
        == 1
    )
    # Cause B has no complaint carrying that resolution.
    assert (
        _total(svc, root_cause_ids=[seeded["rc_b"].id], resolution_ids=[seeded["res"].id])
        == 0
    )


def test_filter_composes_with_status(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    assert _total(svc, root_cause_ids=[seeded["rc_b"].id], status="closed") == 1
    assert _total(svc, root_cause_ids=[seeded["rc_b"].id], status="approved") == 0


def test_unknown_id_returns_empty_not_error(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    assert _total(svc, root_cause_ids=["3f0d7c7e-0000-4000-8000-000000000000"]) == 0


def test_empty_and_blank_values_mean_no_filter(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    baseline = _total(svc)
    assert baseline >= 4
    # An empty list, and a list of blanks, must not narrow the result set.
    assert _total(svc, root_cause_ids=[]) == baseline
    assert _total(svc, root_cause_ids=["", "  "]) == baseline
    assert _total(svc, root_cause_ids=None) == baseline


def test_complaints_with_no_root_cause_are_excluded_when_filtering(db: Session, seeded) -> None:
    svc = ComplaintService(db)
    numbers = {
        row["complaint_number"]
        for row in svc.list_complaints(
            page=1, limit=50, root_cause_ids=[seeded["rc_a"].id]
        )["data"]
    }
    assert numbers == {f"{_MARK}-A1", f"{_MARK}-A2"}
    assert f"{_MARK}-NONE" not in numbers


def test_neighbours_honours_the_same_filter(db: Session, seeded) -> None:
    """The detail pager must walk the filtered set, not the whole table."""
    svc = ComplaintService(db)
    target = (
        db.query(Complaint).filter(Complaint.complaint_number == f"{_MARK}-A1").first()
    )
    out = svc.neighbours(complaint_id=target.id, root_cause_ids=[seeded["rc_a"].id])
    assert out["total"] == 2


class TestCsvIds:
    """The route-level parser for the comma-separated query params."""

    def test_none_and_blank_become_none(self) -> None:
        assert _csv_ids(None) is None
        assert _csv_ids("") is None
        assert _csv_ids("  ") is None
        assert _csv_ids(",,") is None

    def test_splits_and_strips(self) -> None:
        assert _csv_ids("a, b ,,c") == ["a", "b", "c"]

    def test_single_value(self) -> None:
        assert _csv_ids("abc") == ["abc"]
